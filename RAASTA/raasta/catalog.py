"""Syllabus skill graphs.

A skill graph is what turns "help me study" into an actual plan. Each node is a
small, testable capability with prerequisites; the scheduler uses the edges to
decide *where to start* — which matters enormously in Pakistan, where a Class 10
student may still be missing Class 5 foundations.

These graphs are data, not code. Replacing them with the official Punjab / Sindh /
KPK / Balochistan / FBISE / CIE breakdowns is a content task, not an engineering
one — and it is the single highest-value content investment for the product.
"""
from __future__ import annotations

from typing import Dict, List

from .scheduler import Skill


def _s(*specs) -> Dict[str, Skill]:
    out: Dict[str, Skill] = {}
    for spec in specs:
        out[spec.id] = spec
    return out


# ---------------------------------------------------------------------------
# Matric (Class 9-10) — Physics: the classic wall
# ---------------------------------------------------------------------------

MATRIC_PHYSICS: Dict[str, Skill] = _s(
    # --- foundations (often missing; Class 6-8 material) --------------------
    Skill("units_si", "Physics", "SI units aur unka conversion",
          minutes=3.0, difficulty=0.20, exam_weight=0.6, kind="recall"),
    Skill("algebra_rearrange", "Physics", "Formula ko rearrange karna (subject banana)",
          minutes=4.0, difficulty=0.30, exam_weight=1.4, kind="procedure"),
    Skill("graph_reading", "Physics", "Graph padhna: slope aur area",
          minutes=5.0, difficulty=0.45, exam_weight=1.0, kind="procedure"),
    Skill("sig_figs", "Physics", "Significant figures aur rounding",
          minutes=3.0, difficulty=0.25, exam_weight=0.5, kind="procedure"),

    # --- kinematics ---------------------------------------------------------
    Skill("motion_scalar_vector", "Physics", "Scalar vs vector mein farq",
          prereqs=("units_si",), minutes=3.0, difficulty=0.25, exam_weight=0.8),
    Skill("motion_distance_displacement", "Physics", "Distance vs displacement",
          prereqs=("motion_scalar_vector",), minutes=3.5, difficulty=0.35,
          exam_weight=1.0),
    Skill("motion_speed_velocity", "Physics", "Speed aur velocity",
          prereqs=("motion_distance_displacement",), minutes=4.0, difficulty=0.40,
          exam_weight=1.2),
    Skill("motion_acceleration", "Physics", "Acceleration aur uski unit",
          prereqs=("motion_speed_velocity",), minutes=4.5, difficulty=0.50,
          exam_weight=1.4),
    Skill("motion_eqns", "Physics", "Teen equations of motion ka istemal",
          prereqs=("motion_acceleration", "algebra_rearrange"), minutes=7.0,
          difficulty=0.65, exam_weight=2.0, kind="procedure"),
    Skill("motion_graphs", "Physics", "Distance-time aur speed-time graphs",
          prereqs=("motion_eqns", "graph_reading"), minutes=6.0, difficulty=0.60,
          exam_weight=1.6),
    Skill("motion_free_fall", "Physics", "Free fall aur g = 10 m/s²",
          prereqs=("motion_eqns",), minutes=5.0, difficulty=0.55, exam_weight=1.4),

    # --- forces -------------------------------------------------------------
    Skill("force_newton1", "Physics", "Newton ka pehla qanoon (inertia)",
          prereqs=("motion_acceleration",), minutes=3.5, difficulty=0.35,
          exam_weight=1.0),
    Skill("force_newton2", "Physics", "Newton ka doosra qanoon: F = ma",
          prereqs=("force_newton1", "algebra_rearrange"), minutes=6.0,
          difficulty=0.60, exam_weight=2.0, kind="procedure"),
    Skill("force_newton3", "Physics", "Newton ka teesra qanoon (action/reaction)",
          prereqs=("force_newton2",), minutes=3.5, difficulty=0.40, exam_weight=1.2),
    Skill("force_friction", "Physics", "Friction: static vs kinetic",
          prereqs=("force_newton2",), minutes=5.0, difficulty=0.55, exam_weight=1.2),
    Skill("force_momentum", "Physics", "Momentum aur conservation of momentum",
          prereqs=("force_newton2",), minutes=6.5, difficulty=0.65, exam_weight=1.6),
    Skill("force_gravity", "Physics", "Universal gravitation aur weight",
          prereqs=("force_newton2",), minutes=5.0, difficulty=0.55, exam_weight=1.3),

    # --- work, energy, power -------------------------------------------------
    Skill("work_energy_work", "Physics", "Work = F·d aur conditions of work",
          prereqs=("force_newton2",), minutes=4.5, difficulty=0.50, exam_weight=1.4),
    Skill("work_energy_ke", "Physics", "Kinetic energy: ½mv²",
          prereqs=("work_energy_work", "algebra_rearrange"), minutes=5.0,
          difficulty=0.55, exam_weight=1.6, kind="procedure"),
    Skill("work_energy_pe", "Physics", "Gravitational potential energy: mgh",
          prereqs=("work_energy_work",), minutes=4.0, difficulty=0.45, exam_weight=1.4),
    Skill("work_energy_conservation", "Physics", "Energy conservation ke sawal",
          prereqs=("work_energy_ke", "work_energy_pe"), minutes=7.0, difficulty=0.70,
          exam_weight=2.0, kind="procedure"),
    Skill("work_energy_power", "Physics", "Power aur efficiency",
          prereqs=("work_energy_work",), minutes=4.5, difficulty=0.50, exam_weight=1.2),
)


# ---------------------------------------------------------------------------
# Matric Mathematics — the foundation everything else leans on
# ---------------------------------------------------------------------------

MATRIC_MATH: Dict[str, Skill] = _s(
    Skill("num_fractions", "Mathematics", "Fractions: add, subtract, multiply, divide",
          minutes=3.5, difficulty=0.25, exam_weight=1.2, kind="procedure"),
    Skill("num_decimals", "Mathematics", "Decimals aur place value",
          minutes=2.5, difficulty=0.20, exam_weight=0.8, kind="procedure"),
    Skill("num_percent", "Mathematics", "Percentage aur uske sawal",
          prereqs=("num_fractions", "num_decimals"), minutes=4.0, difficulty=0.35,
          exam_weight=1.4, kind="procedure"),
    Skill("alg_variables", "Mathematics", "Variables aur expressions",
          minutes=3.0, difficulty=0.25, exam_weight=1.0),
    Skill("alg_linear_eq", "Mathematics", "Linear equation solve karna",
          prereqs=("alg_variables", "num_fractions"), minutes=5.0, difficulty=0.40,
          exam_weight=1.8, kind="procedure"),
    Skill("alg_simultaneous", "Mathematics", "Do equations, do unknowns",
          prereqs=("alg_linear_eq",), minutes=6.5, difficulty=0.60, exam_weight=1.8,
          kind="procedure"),
    Skill("alg_quadratic_factor", "Mathematics", "Quadratic ko factor karna",
          prereqs=("alg_linear_eq",), minutes=6.0, difficulty=0.60, exam_weight=1.8,
          kind="procedure"),
    Skill("alg_quadratic_formula", "Mathematics", "Quadratic formula",
          prereqs=("alg_quadratic_factor",), minutes=5.5, difficulty=0.65,
          exam_weight=1.6, kind="procedure"),
    Skill("alg_exponents", "Mathematics", "Laws of exponents",
          minutes=4.0, difficulty=0.40, exam_weight=1.4, kind="procedure"),
    Skill("alg_logarithms", "Mathematics", "Logarithms aur unke qawaneen",
          prereqs=("alg_exponents",), minutes=6.0, difficulty=0.60, exam_weight=1.6),
    Skill("geo_pythagoras", "Mathematics", "Pythagoras theorem",
          prereqs=("alg_variables",), minutes=4.5, difficulty=0.45, exam_weight=1.4),
    Skill("geo_trig_ratios", "Mathematics", "sin, cos, tan ratios",
          prereqs=("geo_pythagoras",), minutes=5.5, difficulty=0.55, exam_weight=1.6),
    Skill("geo_trig_heights", "Mathematics", "Heights and distances ke sawal",
          prereqs=("geo_trig_ratios",), minutes=6.5, difficulty=0.65, exam_weight=1.4,
          kind="procedure"),
)


# ---------------------------------------------------------------------------
# MDCAT Biology — high-weight, high-memorisation
# ---------------------------------------------------------------------------

MDCAT_BIOLOGY: Dict[str, Skill] = _s(
    Skill("bio_cell_structure", "Biology", "Cell ke hisson ka naam aur kaam",
          minutes=4.0, difficulty=0.35, exam_weight=1.6, kind="recall"),
    Skill("bio_cell_organelles", "Biology", "Organelles: mitochondria, ribosome, etc.",
          prereqs=("bio_cell_structure",), minutes=5.5, difficulty=0.50,
          exam_weight=1.8, kind="recall"),
    Skill("bio_cell_division_mitosis", "Biology", "Mitosis ke phases",
          prereqs=("bio_cell_structure",), minutes=6.0, difficulty=0.55,
          exam_weight=1.6),
    Skill("bio_cell_division_meiosis", "Biology", "Meiosis aur crossing over",
          prereqs=("bio_cell_division_mitosis",), minutes=6.5, difficulty=0.65,
          exam_weight=1.8),
    Skill("bio_genetics_mendel", "Biology", "Mendel ke qawaneen",
          minutes=5.0, difficulty=0.50, exam_weight=2.0, kind="procedure"),
    Skill("bio_genetics_punnett", "Biology", "Punnett square se crosses",
          prereqs=("bio_genetics_mendel",), minutes=6.0, difficulty=0.55,
          exam_weight=2.0, kind="procedure"),
    Skill("bio_dna_structure", "Biology", "DNA ki structure aur base pairing",
          minutes=5.0, difficulty=0.45, exam_weight=1.8, kind="recall"),
    Skill("bio_protein_synthesis", "Biology", "Transcription aur translation",
          prereqs=("bio_dna_structure", "bio_cell_organelles"), minutes=7.0,
          difficulty=0.70, exam_weight=2.0),
    Skill("bio_enzymes", "Biology", "Enzymes: structure, factors, inhibitors",
          minutes=5.5, difficulty=0.55, exam_weight=1.8),
    Skill("bio_photosynthesis", "Biology", "Photosynthesis: light aur dark reaction",
          prereqs=("bio_cell_organelles",), minutes=6.5, difficulty=0.62,
          exam_weight=1.8),
    Skill("bio_respiration", "Biology", "Aerobic aur anaerobic respiration",
          prereqs=("bio_cell_organelles",), minutes=6.0, difficulty=0.60,
          exam_weight=1.6),
    Skill("bio_human_heart", "Biology", "Heart ki structure aur blood circulation",
          minutes=6.0, difficulty=0.55, exam_weight=2.0),
    Skill("bio_human_kidney", "Biology", "Kidney aur nephron ka kaam",
          minutes=6.0, difficulty=0.60, exam_weight=1.6),
    Skill("bio_nervous_system", "Biology", "Neuron aur reflex arc",
          minutes=5.5, difficulty=0.55, exam_weight=1.6),
)


CATALOGS: Dict[str, Dict[str, Skill]] = {
    "matric_physics": MATRIC_PHYSICS,
    "matric_math": MATRIC_MATH,
    "mdcat_biology": MDCAT_BIOLOGY,
}
# everything at once — used for demos and for students who are genuinely
# preparing across subjects (e.g. Matric Science group)
CATALOGS["all"] = {**MATRIC_PHYSICS, **MATRIC_MATH, **MDCAT_BIOLOGY}

DEFAULT_CATALOG = "matric_physics"


def load_catalog(name: str = DEFAULT_CATALOG) -> Dict[str, Skill]:
    if name not in CATALOGS:
        raise KeyError(f"unknown catalog '{name}'. Available: {', '.join(CATALOGS)}")
    return dict(CATALOGS[name])


def combined(*names: str) -> Dict[str, Skill]:
    out: Dict[str, Skill] = {}
    for n in names or (DEFAULT_CATALOG,):
        out.update(load_catalog(n))
    return out


def catalog_stats(catalog: Dict[str, Skill]) -> Dict[str, float]:
    subjects: Dict[str, int] = {}
    for s in catalog.values():
        subjects[s.subject] = subjects.get(s.subject, 0) + 1
    total_min = sum(s.minutes for s in catalog.values())
    return {"skills": float(len(catalog)), "total_minutes": total_min,
            **{f"subject:{k}": float(v) for k, v in subjects.items()}}
