#!/usr/bin/env python3
"""Score a document's sections for process ceremony with the TypeSafe Jev agent.

The document is split on markdown headings, then on paragraphs, so every Jev
request stays under MAX_REQUEST_BYTES. Every section is asked the same Choice
questions; the verdict is computed here from the answers, never by Jev.
"""
import argparse
import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time

MODEL = "jev-1.13.0"
HOST = "api.typesafe.ai"
PATH = "/v1/systemone"
MAX_REQUEST_BYTES = 24000  # Conservative transport bound, not a vendor token count.
MAX_RESPONSE_BYTES = 1048576

RULES = (
    "Purpose of agent work: working, deployable capability. Process serves that outcome and is never the product. "
    "Boundary test: if running code branches on an artifact, it is product state; if only people or status reports read it, it is process. "
    "Code written only so that something branches on the artifact does not count. "
    "A process artifact (certificate, ledger, dashboard, matrix, meta-report, readiness review, conformance check, review round) is justified "
    "only when it names all four: a concrete consumer, the gate it enforces, an observed (not speculative) defect class, and a retirement condition. "
    "An explicit operator request counts as consumer and gate. A minimal crash-recovery or provenance control that prevents a named data-loss mode is allowed. "
    "Smells: new ledgers or dashboards while delivered features stay flat; closing items with refusal or error paths only; "
    "test, validator or gate changes inside feature work; mocks, fixtures or self-review presented as live proof; "
    "in-scope acceptance split into follow-up items so the original can close; governance or schema review rounds about the process apparatus itself."
)

YES_NO = {"yes": "the section clearly does this", "no": "the section clearly does not",
          "insufficient": "the section does not contain enough to tell"}

QUESTIONS = {
    "artifact_gate": {
        "instructions": "Apply the boundary test and the four-part justification to this section only. Does it create or require a process artifact, and is that artifact justified?",
        "criteria": {
            "none": "no process artifact is created or required",
            "justified": "a process artifact is required and the section names consumer, gate, observed defect and retirement, or an operator request",
            "unjustified": "a process artifact is required without all four parts",
            "insufficient": "the section does not contain enough to tell",
        },
        "flag": ["unjustified"],
    },
    "capability_share": {
        "instructions": "Rank this section by what it spends its words on: specifying or delivering working capability, or describing process around the work.",
        "criteria": {
            "capability": "mostly capability: behavior, interfaces, code, tests of real behavior",
            "mixed": "capability and process in similar measure",
            "process": "mostly process: tracking, reporting, approvals, reviews, status",
            "insufficient": "the section does not contain enough to tell",
        },
        "flag": [],  # Informational: a rules document is process by nature; that alone is not ceremony.
    },
    "gate_weakening": {
        "instructions": "Does this section weaken, bypass or self-certify a test or gate, or accept mocks, fixtures or self-review as proof of live behavior?",
        "criteria": YES_NO, "flag": ["yes"],
    },
    "follow_up_laundering": {
        "instructions": "Does this section move in-scope acceptance conditions into follow-up items so the original item can close?",
        "criteria": YES_NO, "flag": ["yes"],
    },
    "meta_trap": {
        "instructions": "Does this section add review, governance or schema rounds about the process apparatus itself rather than about the deliverable?",
        "criteria": YES_NO, "flag": ["yes"],
    },
}


class JevError(Exception):
    def __init__(self, code, message, recoverable=False):
        super().__init__(message)
        self.code, self.message, self.recoverable = code, message, recoverable


def api_key():
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise JevError("JEV.UNAVAILABLE", "TYPESAFE_API_KEY is missing; no Jev evaluation ran", True)
    if not key.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in key):
        raise JevError("JEV.UNAVAILABLE", "TYPESAFE_API_KEY has invalid formatting")
    return key


def build_request(document, section):
    questions = {qid: {"type": "choice", "instructions": q["instructions"], "criteria": q["criteria"]}
                 for qid, q in QUESTIONS.items()}
    state = {"rules": RULES, "document": document, "section_path": section["path"], "section": section["text"]}
    return {"model": MODEL, "state": state, "questions": questions}


def encode(request):
    return json.dumps(request, allow_nan=False).encode("utf-8")


def split_sections(text):
    """Split markdown into heading-scoped sections, each carrying its heading path."""
    sections, stack, lines = [], [], []

    def flush():
        body = "\n".join(lines).strip()
        if any(not re.match(r"^#{1,6}\s", l) for l in body.splitlines() if l.strip()):
            sections.append({"path": " > ".join(h for _, h in stack) or "(preamble)", "text": body})
        lines.clear()

    fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        match = None if fence else re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if match:
            flush()
            level = len(match.group(1))
            stack[:] = [(lvl, h) for lvl, h in stack if lvl < level] + [(level, match.group(2))]
        lines.append(line)
    flush()
    return sections


def fit_sections(document, sections, limit=MAX_REQUEST_BYTES):
    """Split any section whose request exceeds the limit on paragraph, then line, boundaries."""
    fitted = []
    for section in sections:
        pending = [section["text"]]
        part = 0
        while pending:
            text = pending.pop(0)
            candidate = {"path": section["path"], "text": text}
            if len(encode(build_request(document, candidate))) <= limit:
                part += 1
                fitted.append(candidate)
                continue
            pieces = re.split(r"\n\s*\n", text) if "\n\n" in text else text.splitlines()
            if len(pieces) < 2:
                raise JevError("JEV.INCONCLUSIVE", f"A single line in '{section['path']}' exceeds {limit} bytes; split it by hand without dropping content")
            half = len(pieces) // 2
            sep = "\n\n" if "\n\n" in text else "\n"
            pending[:0] = [sep.join(pieces[:half]), sep.join(pieces[half:])]
        if part > 1:
            for i, s in enumerate(fitted[-part:], 1):
                s["path"] = f"{section['path']} (part {i}/{part})"
    return fitted


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def validate_response(value, request):
    if not isinstance(value, dict) or value.get("model") != MODEL:
        raise JevError("JEV.RESPONSE_INVALID", "Unexpected Jev response model or shape")
    answers = value.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
        raise JevError("JEV.RESPONSE_INVALID", "Missing or unexpected answer IDs")
    for qid, question in request["questions"].items():
        answer, options = answers[qid], set(question["criteria"])
        probs = answer.get("probabilities") if isinstance(answer, dict) else None
        if (not isinstance(answer, dict) or answer.get("type") != "choice"
                or answer.get("choice") not in options
                or not probability(answer.get("confidence"))
                or not isinstance(probs, dict) or set(probs) != options
                or not all(probability(p) for p in probs.values())
                or abs(sum(probs.values()) - 1) > 0.001):
            raise JevError("JEV.RESPONSE_INVALID", f"Invalid Choice answer for {qid}")
    return value


def post(body, key):
    for attempt in range(2):
        conn = http.client.HTTPSConnection(HOST, timeout=30)
        try:
            conn.request("POST", PATH, body=body, headers={
                "Authorization": "Bearer " + key, "Content-Type": "application/json"})
            response = conn.getresponse()
            status, raw = response.status, response.read(MAX_RESPONSE_BYTES + 1)
            retry_after = response.getheader("Retry-After")
        except (OSError, socket.timeout, http.client.HTTPException):
            raise JevError("JEV.UNAVAILABLE", "Jev connection failed or timed out", True) from None
        finally:
            conn.close()
        if status in (429, 529) and attempt == 0:
            try:
                delay = float(retry_after) if retry_after is not None else 1.0
            except ValueError:
                delay = float("inf")
            if math.isfinite(delay) and 0 <= delay <= 5:
                time.sleep(delay)
                continue
        if status != 200:
            raise JevError("JEV.UNAVAILABLE", f"Jev HTTP {status}; response body withheld", status in (429, 529) or status >= 500)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise JevError("JEV.RESPONSE_INVALID", "Jev response exceeded size limit")
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise JevError("JEV.RESPONSE_INVALID", "Jev response was not JSON") from None
    raise JevError("JEV.UNAVAILABLE", "Jev retry budget exhausted", True)


def evaluate(request, key, transport=post):
    body = encode(request)
    if len(body) > MAX_REQUEST_BYTES:
        raise JevError("JEV.INCONCLUSIVE", f"Request exceeds {MAX_REQUEST_BYTES} bytes; split evidence without dropping checks")
    return validate_response(transport(body, key), request)


def score_section(section, answers, minimum_probability):
    flags, low = [], []
    for qid, spec in QUESTIONS.items():
        answer = answers[qid]
        choice = answer["choice"]
        prob = answer["probabilities"][choice]
        if not spec["flag"]:
            continue
        if prob < minimum_probability or choice == "insufficient":
            low.append(qid)
        elif choice in spec["flag"]:
            flags.append(qid)
    status = "ceremony" if flags else "needs_context" if low else "clean"
    return {"path": section["path"], "status": status, "flags": flags, "low_confidence": low,
            "answers": {qid: {"choice": a["choice"], "probability": a["probabilities"][a["choice"]]}
                        for qid, a in answers.items()}}


def aggregate(results):
    counts = {s: sum(r["status"] == s for r in results) for s in ("ceremony", "needs_context", "clean")}
    verdict = "ceremony" if counts["ceremony"] else "needs_context" if counts["needs_context"] else "clean"
    return {"verdict": verdict, "sections": len(results), "counts": counts, "results": results}


def run(path, minimum_probability=0.8, transport=post, key=None):
    text = Path(path).read_text(encoding="utf-8")
    sections = fit_sections(Path(path).name, split_sections(text))
    if not sections:
        raise JevError("VALIDATION.INPUT", "Document has no content")
    key = key if key is not None else api_key()
    results = [score_section(s, evaluate(build_request(Path(path).name, s), key, transport)["answers"], minimum_probability)
               for s in sections]
    return aggregate(results)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--minimum-probability", type=float, default=0.8)
    parser.add_argument("--dry-run", action="store_true", help="print the split sections and request sizes; no Jev call")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            name = args.document.name
            sections = fit_sections(name, split_sections(args.document.read_text(encoding="utf-8")))
            data = {"sections": [{"path": s["path"], "request_bytes": len(encode(build_request(name, s)))} for s in sections]}
        else:
            data = run(args.document, args.minimum_probability)
        result = {"success": True, "data": data, "error": None}
    except JevError as exc:
        result = {"success": False, "data": None, "error": {"code": exc.code, "message": exc.message, "recoverable": exc.recoverable}}
    except (OSError, UnicodeError):
        result = {"success": False, "data": None, "error": {"code": "VALIDATION.INPUT", "message": "Document unavailable or not UTF-8", "recoverable": False}}
    print(json.dumps(result, indent=2, allow_nan=False))
    if not result["success"]:
        return 2
    return 1 if result["data"].get("verdict") == "ceremony" else 0


if __name__ == "__main__":
    sys.exit(main())
