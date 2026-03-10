"""
Economic Optimization Layer
============================
Standalone component that transforms risk assessments into financial
decisions, finds the optimal intervention threshold and quantifies savings.

Architecture (§4.8 ARCHITECTURE.md)
-------------------------------------
Purpose
    Transform technical risk outputs into financial decisions.

Parameters (environment variables, all with defaults)
    C_EARLY       float  cost of early / preventive maintenance   (default 1 000 €)
    C_LATE        float  cost of unplanned failure / late repair   (default 10 000 €)
    DOWNTIME_COST float  additional downtime impact per event      (default 5 000 €)

Input
    MQTT ``cmapss/economic`` carrying ``RISK_ASSESSMENTS`` payloads from
    RiskDecisionEngine.  Also reads risk_assessment_{unit_id}.json files
    from ``data/metrics_and_results/`` on startup.

Processing
    For every batch of unit assessments:

    1. E(Cost) per threshold
       For each θ ∈ {0.10, 0.15, …, 0.90}:
           P_intervene(θ) = fraction of units where risk_score ≥ θ
           P_late   = 1 − P_intervene
           P_early  = P_intervene
           E_cost(θ) = P_late × (C_late + downtime) + P_early × C_early

    2. Optimal threshold
           θ* = argmin E_cost(θ)

    3. Expected annual savings vs. baseline
       Baseline = always-fix strategy → pay C_early for every unit every
       cycle.  Savings = baseline_cost − E_cost(θ*).

    4. Cost sensitivity analysis
       Vary C_late/C_early ratio across a grid and record θ* and E_cost(θ*)
       for each combination → sensitivity_matrix list.

Output
    • Persists  ``data/metrics_and_results/economic_analysis_{dataset_id}.json``
    • Publishes summary to ``cmapss/monitoring``

MQTT
    Subscribe : ``cmapss/economic``
    Publish   : ``cmapss/monitoring``

Component base
    ``PipelineComponent`` from ``src.common.components``
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from configs import config
from src.common.components import PipelineComponent

# ---------------------------------------------------------------------------
# MQTT topics
# ---------------------------------------------------------------------------
SUBSCRIBE_TOPIC: str = config.MQTT["TOPICS"]["ECONOMIC"]
PUBLISH_TOPIC: str = config.MQTT["TOPICS"]["MONITORING"]

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
_OUTPUT_DIR: str = config.DATA.get("METRICS_AND_RESULTS", "data/metrics_and_results")

# ---------------------------------------------------------------------------
# Default cost parameters
# ---------------------------------------------------------------------------
_DEFAULT_C_EARLY: float = 1_000.0
_DEFAULT_C_LATE: float = 10_000.0
_DEFAULT_DOWNTIME: float = 5_000.0

# Threshold grid: 0.10 to 0.90 inclusive, step 0.05
_THRESHOLD_GRID: List[float] = [round(0.10 + 0.05 * i, 2) for i in range(17)]

# Sensitivity grid: ratios C_late / C_early to explore
_SENSITIVITY_RATIOS: List[float] = [2.0, 5.0, 10.0, 20.0, 50.0, 100.0]

logger = logging.getLogger(__name__)


# ===========================================================================
# Pure computation helpers
# ===========================================================================

def expected_cost(
    p_late: float,
    p_early: float,
    c_late: float,
    c_early: float,
    downtime: float,
) -> float:
    """
    E[Cost] = P_late × (C_late + downtime) + P_early × C_early

    Parameters
    ----------
    p_late    : probability of not intervening (late failure)
    p_early   : probability of preventive intervention
    c_late    : cost of unplanned failure (€)
    c_early   : cost of planned maintenance (€)
    downtime  : additional downtime cost per failure event (€)
    """
    return round(p_late * (c_late + downtime) + p_early * c_early, 4)


def cost_curve(
    risk_scores: List[float],
    c_early: float,
    c_late: float,
    downtime: float,
    thresholds: Optional[List[float]] = None,
) -> List[Dict]:
    """
    Compute E[Cost] at every threshold in the grid.

    For each threshold θ:
        • units with risk_score ≥ θ are intervened on (P_early)
        • remaining units are left to potentially fail (P_late)

    Returns
    -------
    list of dicts: {threshold, p_intervene, p_late, expected_cost_eur}
    sorted by threshold ascending.
    """
    if thresholds is None:
        thresholds = _THRESHOLD_GRID
    n = len(risk_scores)
    if n == 0:
        return []

    results = []
    for theta in thresholds:
        n_intervene = sum(1 for s in risk_scores if s >= theta)
        p_early = n_intervene / n
        p_late = 1.0 - p_early
        ec = expected_cost(p_late, p_early, c_late, c_early, downtime)
        results.append(
            {
                "threshold": theta,
                "p_intervene": round(p_early, 4),
                "p_late": round(p_late, 4),
                "expected_cost_eur": ec,
            }
        )
    return results


def find_optimal_threshold(curve: List[Dict]) -> Dict:
    """
    θ* = argmin E[Cost] over the cost curve.

    Returns the curve entry with the minimum expected_cost_eur.
    """
    if not curve:
        return {}
    return min(curve, key=lambda x: x["expected_cost_eur"])


def baseline_cost(
    n_units: int,
    c_early: float,
) -> float:
    """
    Always-fix baseline: every unit gets preventive maintenance every cycle.
    Baseline = n_units × C_early.
    """
    return round(n_units * c_early, 4)


def annual_savings(
    n_units: int,
    optimal_ec: float,
    c_early: float,
    cycles_per_year: int = 365,
) -> Dict:
    """
    Compare the optimal strategy against two baselines over a full year.

    Baselines
    ---------
    always_maintain : pay C_early for every unit, every cycle
    always_reactive : pay C_late for every unit whenever it fails (every cycle)

    Returns
    -------
    dict with: baseline_always_maintain_eur, baseline_always_reactive_eur,
               optimal_annual_eur, savings_vs_maintain_eur, savings_vs_reactive_eur,
               cycles_per_year
    """
    bl_maintain = round(n_units * c_early * cycles_per_year, 2)
    # Reactive baseline: all units fail every cycle (worst case)
    c_late = optimal_ec  # use as proxy; caller may override
    bl_reactive = round(n_units * c_late * cycles_per_year, 2)
    optimal_annual = round(optimal_ec * cycles_per_year, 2)

    return {
        "baseline_always_maintain_eur": bl_maintain,
        "baseline_always_reactive_eur": bl_reactive,
        "optimal_annual_eur": optimal_annual,
        "savings_vs_maintain_eur": round(max(bl_maintain - optimal_annual, 0.0), 2),
        "savings_vs_reactive_eur": round(max(bl_reactive - optimal_annual, 0.0), 2),
        "cycles_per_year": cycles_per_year,
    }


def sensitivity_analysis(
    risk_scores: List[float],
    c_early_base: float,
    downtime: float,
    ratios: Optional[List[float]] = None,
) -> List[Dict]:
    """
    Vary the C_late / C_early ratio and record θ* and E_cost(θ*)
    for each combination.

    The base C_early is kept fixed; C_late is derived as ratio × C_early.

    Returns
    -------
    list of dicts: {ratio, c_early, c_late, optimal_threshold, optimal_cost_eur,
                    p_intervene_at_optimal}
    """
    if ratios is None:
        ratios = _SENSITIVITY_RATIOS
    matrix = []
    for ratio in ratios:
        c_late_var = round(c_early_base * ratio, 2)
        curve = cost_curve(risk_scores, c_early_base, c_late_var, downtime)
        opt = find_optimal_threshold(curve)
        matrix.append(
            {
                "ratio_c_late_over_c_early": ratio,
                "c_early_eur": c_early_base,
                "c_late_eur": c_late_var,
                "optimal_threshold": opt.get("threshold"),
                "optimal_cost_eur": opt.get("expected_cost_eur"),
                "p_intervene_at_optimal": opt.get("p_intervene"),
            }
        )
    return matrix


def run_full_analysis(
    assessments: List[Dict],
    c_early: float,
    c_late: float,
    downtime: float,
    dataset_id: str = "",
) -> Dict:
    """
    Full economic analysis pipeline for a batch of unit assessments.

    Parameters
    ----------
    assessments : list of risk_assessment dicts from RiskDecisionEngine
    c_early     : cost of early maintenance (€)
    c_late      : cost of late failure (€)
    downtime    : downtime cost per event (€)
    dataset_id  : identifier for logging / file naming

    Returns
    -------
    Complete analysis document (ready to persist as JSON).
    """
    risk_scores = [float(a.get("risk_score", 0.0)) for a in assessments]
    failure_probs = [float(a.get("failure_prob_at_horizon", 0.0)) for a in assessments]
    n = len(risk_scores)

    if n == 0:
        return {
            "dataset_id": dataset_id,
            "error": "No unit assessments provided",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # 1. Cost curve over threshold grid
    curve = cost_curve(risk_scores, c_early, c_late, downtime)

    # 2. Optimal threshold
    opt = find_optimal_threshold(curve)
    opt_theta = opt.get("threshold", 0.5)
    opt_cost = opt.get("expected_cost_eur", 0.0)

    # 3. Mean failure probability across fleet
    mean_fp = round(sum(failure_probs) / n, 6) if failure_probs else 0.0

    # 4. Annual savings (use optimal per-cycle cost × 365 vs always-fix baseline)
    savings = annual_savings(n, opt_cost, c_early, cycles_per_year=365)
    # Fix the reactive baseline: use (c_late + downtime) as reactive cost per unit
    savings["baseline_always_reactive_eur"] = round(
        n * (c_late + downtime) * 365, 2
    )
    savings["savings_vs_reactive_eur"] = round(
        max(savings["baseline_always_reactive_eur"] - savings["optimal_annual_eur"], 0.0), 2
    )

    # 5. Sensitivity matrix
    sens = sensitivity_analysis(risk_scores, c_early, downtime)

    # 6. Per-unit summary (unit_id, risk_score, failure_prob, recommended action)
    unit_summary = [
        {
            "unit_id": a.get("unit_id"),
            "risk_score": a.get("risk_score"),
            "failure_prob": a.get("failure_prob_at_horizon"),
            "maintenance_urgency": a.get("maintenance_urgency"),
            "intervention_window_lower": a.get("intervention_window_lower"),
            "intervention_window_upper": a.get("intervention_window_upper"),
            "alert_level": a.get("alert_level"),
        }
        for a in assessments
    ]

    return {
        "type": "ECONOMIC_ANALYSIS",
        "dataset_id": dataset_id,
        "n_units": n,
        "cost_parameters": {
            "c_early_eur": c_early,
            "c_late_eur": c_late,
            "downtime_cost_eur": downtime,
            "total_late_cost_eur": round(c_late + downtime, 2),
        },
        "fleet_summary": {
            "mean_risk_score": round(sum(risk_scores) / n, 6),
            "mean_failure_probability": mean_fp,
            "n_critical": sum(1 for a in assessments if a.get("maintenance_urgency") == "CRITICAL"),
            "n_high": sum(1 for a in assessments if a.get("maintenance_urgency") == "HIGH"),
            "n_medium": sum(1 for a in assessments if a.get("maintenance_urgency") == "MEDIUM"),
            "n_low": sum(1 for a in assessments if a.get("maintenance_urgency") == "LOW"),
        },
        "optimal_policy": {
            "optimal_threshold": opt_theta,
            "expected_cost_per_cycle_eur": opt_cost,
            "p_intervene": opt.get("p_intervene"),
            "p_late": opt.get("p_late"),
        },
        "annual_savings": savings,
        "cost_curve": curve,
        "sensitivity_matrix": sens,
        "unit_summary": unit_summary,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ===========================================================================
# I/O helpers
# ===========================================================================

def _load_risk_assessments_from_disk(output_dir: Path) -> Dict[str, List[Dict]]:
    """
    Read all risk_assessment_{unit_id}.json files from disk.
    Returns a dict {dataset_id: [latest_assessment_per_unit]}.
    """
    by_dataset: Dict[str, List[Dict]] = {}
    for fp in sorted(output_dir.glob("risk_assessment_*.json")):
        try:
            with open(fp) as f:
                records = json.load(f)
            if not isinstance(records, list) or not records:
                continue
            latest = records[-1]
            did = latest.get("dataset_id", "unknown")
            by_dataset.setdefault(did, []).append(latest)
        except Exception as exc:
            logger.warning(f"Could not read {fp.name}: {exc}")
    return by_dataset


def _persist_analysis(analysis: Dict, output_dir: Path) -> Path:
    """Write economic_analysis_{dataset_id}.json (single-document, overwrite)."""
    dataset_id = analysis.get("dataset_id", "unknown")
    # Sanitise dataset_id for filename
    safe_id = str(dataset_id).replace("/", "_").replace("\\", "_").strip("_") or "unknown"
    out_path = output_dir / f"economic_analysis_{safe_id}.json"
    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2)
    return out_path


# ===========================================================================
# PipelineComponent
# ===========================================================================

class EconomicOptimizationLayer(PipelineComponent):
    """
    Economic Optimization Layer (§4.8 ARCHITECTURE.md).

    Subscribes to  ``cmapss/economic``   (RISK_ASSESSMENTS from RiskDecisionEngine)
    Publishes to   ``cmapss/monitoring`` (ECONOMIC_ANALYSIS summary)

    Output file: ``data/metrics_and_results/economic_analysis_{dataset_id}.json``

    Configurable via environment variables
    --------------------------------------
    C_EARLY       float   default 1 000 €
    C_LATE        float   default 10 000 €
    DOWNTIME_COST float   default 5 000 €
    """

    def __init__(
        self,
        c_early: float = _DEFAULT_C_EARLY,
        c_late: float = _DEFAULT_C_LATE,
        downtime_cost: float = _DEFAULT_DOWNTIME,
        output_dir: Optional[str] = None,
    ):
        super().__init__(
            name="EconomicOptimizationLayer",
            mqtt_topic_subscribe_list=[SUBSCRIBE_TOPIC],
        )
        self._c_early: float = float(os.getenv("C_EARLY", str(c_early)))
        self._c_late: float = float(os.getenv("C_LATE", str(c_late)))
        self._downtime: float = float(os.getenv("DOWNTIME_COST", str(downtime_cost)))
        self._output_dir: Path = Path(output_dir or _OUTPUT_DIR)
        self._queue: List[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        super().setup()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(
            f"{self.name}: ready — "
            f"C_EARLY={self._c_early}€  C_LATE={self._c_late}€  "
            f"DOWNTIME={self._downtime}€  "
            f"subscribe={SUBSCRIBE_TOPIC}  publish={PUBLISH_TOPIC}"
        )

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown complete")

    # ------------------------------------------------------------------
    # MQTT callback
    # ------------------------------------------------------------------

    def on_message_received(self, payload: dict) -> None:
        """
        Accept ``RISK_ASSESSMENTS`` batch messages and any payload carrying
        ``assessments`` or a bare ``unit_id`` field.
        """
        msg_type = payload.get("type", "")
        has_assessments = "assessments" in payload
        has_unit = "unit_id" in payload and "risk_score" in payload

        if has_assessments or has_unit or msg_type in (
            "RISK_ASSESSMENTS", "RISK_ASSESSMENT"
        ):
            dataset_id = payload.get("dataset_id", "unknown")
            self.logger.info(
                f"{self.name}: queued economic-analysis request "
                f"type={msg_type!r}  dataset_id={dataset_id!r}"
            )
            self._queue.append(payload)
        else:
            self.logger.debug(
                f"{self.name}: ignored message type={msg_type!r}"
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def execute(self) -> None:
        while self._queue:
            item = self._queue.pop(0)
            try:
                self._process_message(item)
            except Exception as exc:
                self.logger.exception(
                    f"{self.name}: error processing message: {exc}"
                )

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def _process_message(self, payload: dict) -> None:
        """Dispatch a single queued message."""
        assessments: List[Dict] = payload.get("assessments", [])

        # Single-unit message: wrap as a list
        if not assessments and "unit_id" in payload and "risk_score" in payload:
            assessments = [payload]

        if not assessments:
            self.logger.warning(
                f"{self.name}: no assessments found in message"
            )
            return

        dataset_id = payload.get("dataset_id", "unknown")

        analysis = run_full_analysis(
            assessments=assessments,
            c_early=self._c_early,
            c_late=self._c_late,
            downtime=self._downtime,
            dataset_id=dataset_id,
        )

        # Persist full analysis
        out_path = _persist_analysis(analysis, self._output_dir)
        self.logger.info(
            f"{self.name}: analysis complete for dataset_id={dataset_id!r}  "
            f"n_units={analysis['n_units']}  "
            f"optimal_threshold={analysis['optimal_policy']['optimal_threshold']}  "
            f"E_cost*={analysis['optimal_policy']['expected_cost_per_cycle_eur']:.2f}€  "
            f"→ {out_path.name}"
        )

        # Publish a lean summary to cmapss/monitoring
        summary = {
            "type": "ECONOMIC_SUMMARY",
            "dataset_id": dataset_id,
            "n_units": analysis["n_units"],
            "cost_parameters": analysis["cost_parameters"],
            "fleet_summary": analysis["fleet_summary"],
            "optimal_policy": analysis["optimal_policy"],
            "annual_savings": analysis["annual_savings"],
            "generated_at": analysis["generated_at"],
        }
        self.send_message(PUBLISH_TOPIC, summary)
        self.logger.info(
            f"{self.name}: published economic summary → {PUBLISH_TOPIC}"
        )

    # ------------------------------------------------------------------
    # Startup batch: process any existing risk assessments on disk
    # ------------------------------------------------------------------

    def scan_and_process_existing(self) -> None:
        """
        At startup, load all risk_assessment_*.json files from disk and run
        economic analysis for each dataset group that does not already have
        a current economic_analysis file.
        """
        by_dataset = _load_risk_assessments_from_disk(self._output_dir)
        if not by_dataset:
            self.logger.info(
                f"{self.name}: no existing risk assessments on disk — "
                "waiting for MQTT triggers"
            )
            return

        self.logger.info(
            f"{self.name}: found assessments for "
            f"{len(by_dataset)} dataset(s) — running startup analysis…"
        )
        for dataset_id, assessments in by_dataset.items():
            existing = self._output_dir / f"economic_analysis_{dataset_id}.json"
            if existing.exists():
                self.logger.info(
                    f"{self.name}: skipping {dataset_id!r} "
                    "(economic_analysis already exists)"
                )
                continue
            try:
                analysis = run_full_analysis(
                    assessments=assessments,
                    c_early=self._c_early,
                    c_late=self._c_late,
                    downtime=self._downtime,
                    dataset_id=dataset_id,
                )
                out_path = _persist_analysis(analysis, self._output_dir)
                self.logger.info(
                    f"{self.name}: startup analysis for {dataset_id!r} → {out_path.name}"
                )
            except Exception as exc:
                self.logger.warning(
                    f"{self.name}: startup analysis failed for {dataset_id!r}: {exc}"
                )


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    _c_early = float(os.getenv("C_EARLY", str(_DEFAULT_C_EARLY)))
    _c_late = float(os.getenv("C_LATE", str(_DEFAULT_C_LATE)))
    _downtime = float(os.getenv("DOWNTIME_COST", str(_DEFAULT_DOWNTIME)))

    print("\n" + "=" * 65)
    print("💰 [ECONOMIC OPTIMIZATION LAYER CONTAINER ONLINE]")
    print(f"   Subscribe    : {SUBSCRIBE_TOPIC}")
    print(f"   Publish      : {PUBLISH_TOPIC}")
    print(f"   C_EARLY      : {_c_early} €")
    print(f"   C_LATE       : {_c_late} €")
    print(f"   DOWNTIME_COST: {_downtime} €")
    print(f"   Grid         : {_THRESHOLD_GRID[0]} … {_THRESHOLD_GRID[-1]} "
          f"({len(_THRESHOLD_GRID)} steps)")
    print("=" * 65 + "\n")

    component = EconomicOptimizationLayer(
        c_early=_c_early,
        c_late=_c_late,
        downtime_cost=_downtime,
    )
    component.setup()

    # Process any existing risk assessments on disk before entering MQTT loop
    component.scan_and_process_existing()

    try:
        while True:
            component.execute()
            time.sleep(0.5)
    except KeyboardInterrupt:
        component.teardown()
        logging.getLogger(__name__).info(
            "🛑 EconomicOptimizationLayer stopped"
        )

