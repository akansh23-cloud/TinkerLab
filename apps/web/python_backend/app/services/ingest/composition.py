"""Conservative chemical-formula parsing for external ingestion.

The parser exists to prevent a dangerous fallback: assigning stoichiometry 1.0 to every element
when a provider supplies a formula such as Ga2O3.  It supports conventional element/count formulas,
nested parentheses/brackets and hydrate separators.  When a formula cannot be interpreted safely it
returns no composition; callers must preserve the formula string but must not invent coefficients.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_ELEMENTS = frozenset("""
H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr
Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm
Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr
Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
""".split())

_TOKEN = re.compile(r"([A-Z][a-z]?|\d+(?:\.\d+)?|[()\[\]])")


class FormulaParseError(ValueError):
    pass


def _merge(target: dict[str, float], source: dict[str, float], multiplier: float = 1.0) -> None:
    for element, amount in source.items():
        target[element] += amount * multiplier


def _parse_group(formula: str) -> dict[str, float]:
    tokens = _TOKEN.findall(formula)
    if "".join(tokens) != formula:
        raise FormulaParseError(f"Unsupported formula syntax: {formula}")

    stack: list[tuple[dict[str, float], str | None]] = [(defaultdict(float), None)]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"(", "["}:
            stack.append((defaultdict(float), token))
            index += 1
            continue
        if token in {")",
            "]",
        }:
            if len(stack) == 1:
                raise FormulaParseError("Unbalanced closing bracket")
            group, opener = stack.pop()
            expected = ")" if opener == "(" else "]"
            if token != expected:
                raise FormulaParseError("Mismatched brackets")
            multiplier = 1.0
            if index + 1 < len(tokens) and re.fullmatch(r"\d+(?:\.\d+)?", tokens[index + 1]):
                multiplier = float(tokens[index + 1])
                index += 1
            _merge(stack[-1][0], group, multiplier)
            index += 1
            continue
        if re.fullmatch(r"[A-Z][a-z]?", token):
            if token not in _ELEMENTS:
                raise FormulaParseError(f"Unknown element symbol: {token}")
            amount = 1.0
            if index + 1 < len(tokens) and re.fullmatch(r"\d+(?:\.\d+)?", tokens[index + 1]):
                amount = float(tokens[index + 1])
                index += 1
            stack[-1][0][token] += amount
            index += 1
            continue
        # A number may only follow an element or a closed group. Reaching it here is unsafe.
        raise FormulaParseError(f"Unexpected coefficient in formula: {formula}")

    if len(stack) != 1:
        raise FormulaParseError("Unbalanced opening bracket")
    composition = dict(stack[0][0])
    if not composition or any(value <= 0 for value in composition.values()):
        raise FormulaParseError("Formula contains no positive element counts")
    return composition


def parse_formula(formula: str | None) -> dict[str, float]:
    """Return element -> stoichiometric coefficient, or an empty dict when parsing is unsafe.

    Dot-separated hydrates are supported. A leading integer coefficient on a hydrate segment such
    as ``5H2O`` is interpreted as a multiplier for that segment. Decimal stoichiometries remain
    decimal numbers because only the Unicode middle dot is treated as a hydrate separator.
    """
    if not formula:
        return {}
    text = str(formula).strip().replace(" ", "")
    if not text:
        return {}
    # Caret charge notation is unambiguous (SO4^2-). Bare terminal charge notation is not: Fe3+
    # can mean Fe with +3 charge while NH4+ contains a real stoichiometric 4. Fail closed rather
    # than silently turning charge magnitude into composition.
    if re.search(r"\^\d*[+-]$", text):
        text = re.sub(r"\^\d*[+-]$", "", text)
    elif re.search(r"[+-]$", text):
        return {}

    total: dict[str, float] = defaultdict(float)
    try:
        for segment in text.split("·"):
            if not segment:
                raise FormulaParseError("Empty hydrate segment")
            match = re.match(r"^(\d+)(?=[A-Z(\[])", segment)
            multiplier = 1.0
            if match:
                multiplier = float(match.group(1))
                segment = segment[match.end():]
            _merge(total, _parse_group(segment), multiplier)
    except (FormulaParseError, ValueError, OverflowError):
        return {}
    return dict(total)


def state_composition(formula: str | None) -> list[dict[str, Any]]:
    parsed = parse_formula(formula)
    return [
        {"element": element, "role": "host", "stoichiometry": amount,
         "original_representation": formula}
        for element, amount in sorted(parsed.items())
    ]


def identity_composition(formula: str | None) -> list[dict[str, Any]]:
    parsed = parse_formula(formula)
    return [
        {"component_name": element, "amount_basis": "stoichiometric", "amount_value": amount}
        for element, amount in sorted(parsed.items())
    ]
