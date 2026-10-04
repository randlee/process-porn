#!/usr/bin/env python3
"""Locate likely ceremony patterns in sprint plans, CI workflows and agent instructions with the TypeSafe Jev agent.

Each unit (one sprint, one workflow file, or one instruction file) is routed to
Jev on its own. Every item in the unit (a list item, paragraph, table row or
code block of markdown; the header, a job or a step of a workflow) gets one
Choice question whose answer is the pattern that best fits it. Items are packed into
requests under MAX_REQUEST_BYTES with the unit's context repeated in each
request. The report is computed here from the answers.
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
MAX_QUESTIONS = 12
CONTEXT_BYTES = 6000
CALLER_CONTEXT_BYTES = 8000
ROUNDING = 0.005
CI_INVENTORY_BYTES = 12000

CORE = (
    "Purpose of agent work: working, deployable capability. Process serves that outcome and is never the product. "
    "Boundary test: if running code branches on an artifact, it is product state; if only people or status reports read it, it is process. "
    "Code written only so that something branches on the artifact does not count. "
    "A process artifact (certificate, ledger, dashboard, matrix, meta-report, readiness review, conformance check, review round) is justified "
    "only when it names all four: a concrete consumer, the gate it enforces, an observed (not speculative) defect class, and a retirement condition. "
    "An explicit operator request counts as consumer and gate. A minimal crash-recovery or provenance control that prevents a named data-loss mode is allowed. "
    "state.caller_context, when present, holds facts the calling agent collected outside the reviewed text: tools that read fields, "
    "required checks, loaders and enforcement. An item it names as read, required or enforced has that consumer; judge it accordingly. "
)

SITUATIONS = {
    "plan": {
        "rules": CORE + (
            "You are classifying one sprint plan, item by item. Capability items tell the implementer what to build, how it must behave, "
            "which interfaces and paths it touches, or which real tests and validation commands must pass. "
            "Naming work that is out of scope and owned by another named sprint is scope, not follow-up laundering. "
            "The patterns are: ungated process artifacts; review or governance rounds about the process itself; narration (history, provenance, "
            "rationale, status or restatement that gives the implementer no instruction and that nothing checks); items that weaken or self-certify "
            "a test or gate, or accept mocks or self-review as live proof; and items that move in-scope acceptance into a follow-up so the sprint can close."
        ),
        "instructions": "Choose the description that best fits item {id} (state.items.{id}) of the sprint plan in state.unit, using state.rules and state.context.",
        "clear": ("capability", "justified_process"),
        "criteria": {
            "capability": "specifies behavior, interfaces, code, data, owned paths or a test of real behavior the sprint delivers",
            "justified_process": "a process step or validation command that runs and blocks merge, or names consumer, gate, observed defect and retirement",
            "ungated_artifact": "creates or requires a process artifact without consumer, gate, observed defect and retirement",
            "meta_review": "a review, governance or schema round about the process apparatus rather than the deliverable",
            "narration": "history, provenance, rationale, status or restatement that instructs no one and that nothing checks",
            "gate_weakening": "weakens, bypasses or self-certifies a test or gate, or accepts mocks or self-review as live proof",
            "follow_up_laundering": "moves in-scope acceptance into a follow-up so the sprint can close",
            "insufficient": "the item and context are not enough to tell",
        },
    },
    "ci": {
        "rules": CORE + (
            "You are classifying one CI workflow file, item by item: the workflow header (triggers, permissions, concurrency), each job, each step. "
            "state.context lists every job in every reviewed workflow so you can see duplication. "
            "Gates build, lint or test the product and their failure blocks a merge or release; release items build or publish a shipped artifact; "
            "support is setup a gate or release job needs. The patterns are: reports, summaries, badges, uploads and notifications that nothing gates on; "
            "work that another job or step already does for the same trigger; checks whose failure blocks nothing; and items that let failures pass "
            "(continue-on-error, skip conditions, path filters or retries that hide red)."
        ),
        "instructions": "Choose the description that best fits item {id} (state.items.{id}) of the CI workflow in state.unit, using state.rules and state.context.",
        "clear": ("gate", "release", "support"),
        "criteria": {
            "gate": "builds, lints or tests the product and its failure blocks merge or release",
            "release": "builds, signs or publishes a shipped artifact",
            "support": "triggers, permissions or setup (checkout, toolchain, cache) that a gate or release job needs",
            "report_only": "produces a report, summary, badge, upload or notification that nothing gates on",
            "redundant": "repeats work that another job or step in state.context already does for the same trigger",
            "unconsumed_check": "a check whose failure blocks nothing",
            "gate_weakening": "continue-on-error, skip conditions, path filters or retries that let failures pass",
            "insufficient": "the item and context are not enough to tell",
        },
    },
    "instructions": {
        "rules": CORE + (
            "You are classifying one agent instruction file (CLAUDE.md, AGENTS.md, a skill or an agent prompt), item by item. "
            "Every item costs context on every run of the agent that loads it. Instructions change what the agent does: a rule with its trigger, "
            "a step, a command, a path, a format, a limit, or a pointer to a file the agent must read. "
            "The patterns are: telling the agent to create or maintain an ungated process artifact; mandating review or governance rounds about the "
            "process itself; narration (history, incident stories, purpose or motivation sections, rationale beyond what the rule needs, "
            "restatement of a rule already given); telling the agent to weaken, skip or self-certify tests or gates, or to accept mocks or self-review "
            "as live proof; and naming a path or command that state.caller_context records as missing."
        ),
        "instructions": "Choose the description that best fits item {id} (state.items.{id}) of the instruction file in state.unit, using state.rules and state.context.",
        "clear": ("instruction", "reference"),
        "criteria": {
            "instruction": "a rule, step, constraint or trigger that changes what the agent does",
            "reference": "a command, path, format, limit or pointer the agent needs to act, and that exists",
            "ungated_artifact": "tells the agent to create or maintain a process artifact without consumer, gate, observed defect and retirement",
            "meta_review": "mandates a review, governance or approval round about the process rather than the work",
            "narration": "history, incident story, purpose, motivation, excess rationale or restatement that changes no action",
            "gate_weakening": "tells the agent to weaken, skip or self-certify tests or gates, or accept mocks or self-review as live proof",
            "stale_reference": "names a path or command that state.caller_context records as missing",
            "insufficient": "the item and context are not enough to tell",
        },
    },
}


class JevError(Exception):
    def __init__(self, code, message, recoverable=False):
        super().__init__(message)
        self.code, self.message, self.recoverable = code, message, recoverable


def cap(text, limit=CONTEXT_BYTES):
    data = text.encode("utf-8")
    return text if len(data) <= limit else data[:limit].decode("utf-8", "ignore") + "\n[context truncated]"


# ---------- markdown units (plan, instructions) ----------

HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
LIST_START = re.compile(r"^ ?([-*+]|\d+[.)])\s")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")


def md_items(lines, first_line=1, prefix=""):
    """Split markdown lines into items with heading paths and 1-based line ranges."""
    items, stack, cur, fence, table_head = [], [], None, False, None

    def close():
        nonlocal cur
        if cur and any(l.strip() for l in cur["lines"]):
            items.append(cur)
        cur = None

    def start(n, kind, line):
        nonlocal cur
        close()
        path = " > ".join(h for _, h in stack) or "(preamble)"
        cur = {"path": (prefix + " > " + path) if prefix else path, "kind": kind, "start": n, "end": n, "lines": [line]}

    for n, line in enumerate(lines, first_line):
        if fence:
            cur["lines"].append(line)
            cur["end"] = n
            if line.lstrip().startswith("```"):
                fence = False
                close()
            continue
        if line.lstrip().startswith("```"):
            start(n, "code", line)
            fence = True
            continue
        match = HEADING.match(line)
        if match:
            close()
            table_head = None
            level = len(match.group(1))
            stack[:] = [(lvl, h) for lvl, h in stack if lvl < level] + [(level, match.group(2))]
            continue
        if not line.strip():
            close()
            table_head = None
            continue
        if line.lstrip().startswith("|"):
            if TABLE_SEP.match(line):
                continue
            if table_head is None:
                close()
                table_head = line
                continue
            start(n, "table_row", table_head + "\n" + line)
            close()
            continue
        if LIST_START.match(line):
            start(n, "list_item", line)
        elif cur is None:
            start(n, "paragraph", line)
        else:
            cur["lines"].append(line)
            cur["end"] = n
    close()
    return [{"path": i["path"], "kind": i["kind"], "start": i["start"], "end": i["end"], "text": "\n".join(i["lines"])} for i in items]


def outline(lines):
    return "Outline:\n" + "\n".join(l.strip() for l in lines if HEADING.match(l))


def plan_context(lines):
    """Heading outline plus the goal/deliverable/scope sections, capped."""
    picked, keep = [], False
    for line in lines:
        match = HEADING.match(line)
        if match:
            keep = bool(re.search(r"goal|deliverable|scope", match.group(2), re.I))
        if keep:
            picked.append(line)
    return cap(outline(lines) + "\n\nGoal and deliverables:\n" + "\n".join(picked))


def instructions_context(lines):
    """Heading outline plus the text before the first second-level heading (frontmatter, title, intro), capped."""
    first_h2 = next((i for i, l in enumerate(lines) if (m := HEADING.match(l)) and len(m.group(1)) >= 2), len(lines))
    return cap(outline(lines) + "\n\nOpening:\n" + "\n".join(lines[:first_h2]))


def md_units(path, situation, sprint_level=None):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    spans = [(0, len(lines))]
    if situation == "plan" and sprint_level:
        starts = [i for i, l in enumerate(lines) if (m := HEADING.match(l)) and len(m.group(1)) == sprint_level]
        bounds = ([0] if starts[:1] != [0] else []) + starts + [len(lines)]
        spans = [(a, b) for a, b in zip(bounds, bounds[1:]) if any(l.strip() for l in lines[a:b])]
    context = plan_context if situation == "plan" else instructions_context
    units = []
    for a, b in spans:
        chunk = lines[a:b]
        title = next((HEADING.match(l).group(2) for l in chunk if HEADING.match(l)), Path(path).name)
        units.append({"id": f"{Path(path).name}:{title}", "title": title, "source": str(path),
                      "context": context(chunk), "items": md_items(chunk, a + 1)})
    return units


BEAD_FIELDS = ("description", "design", "acceptance_criteria", "notes")


def plan_unit_from_bead(bead):
    title = bead.get("title", "")
    items, fields = [], []
    for field in BEAD_FIELDS:
        lines = (bead.get(field) or "").splitlines()
        items += [dict(i, field=field) for i in md_items(lines, 1, field)]
        fields.append(f"{field}: " + "; ".join(l.strip() for l in lines if HEADING.match(l)))
    metadata = bead.get("metadata") if isinstance(bead.get("metadata"), dict) else {}
    context = cap(f"Title: {title}\nType: {bead.get('issue_type', '')}\nMetadata keys: {', '.join(sorted(metadata))}\n"
                  "Outline:\n" + "\n".join(fields) + "\n\nDescription:\n" + (bead.get("description") or ""))
    return {"id": bead["id"], "title": title, "source": f"bead {bead['id']}", "context": context, "items": items}


def load_beads(path):
    """Read bead objects from a file or '-' (stdin): a bare list, or {"source": "bd"|"br", "beads": [...]}."""
    raw = sys.stdin.read() if str(path) == "-" else Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except ValueError:
        raise JevError("VALIDATION.INPUT", "Bead input is not JSON") from None
    beads = data.get("beads") if isinstance(data, dict) else data
    if not isinstance(beads, list) or not beads:
        raise JevError("VALIDATION.INPUT", "Bead input must be a non-empty list or an object with a non-empty beads list")
    for bead in beads:
        if not isinstance(bead, dict) or not isinstance(bead.get("id"), str) or not bead["id"]:
            raise JevError("VALIDATION.INPUT", "Every bead needs a string id")
        for field in BEAD_FIELDS + ("title",):
            if bead.get(field) is not None and not isinstance(bead[field], str):
                raise JevError("VALIDATION.INPUT", f"Bead {bead['id']} field {field} must be a string")
    return beads


# ---------- ci units ----------

KEY = re.compile(r"^(\s*)([\w.-]+):")


def indent(line):
    return len(line) - len(line.lstrip(" "))


def ci_structure(lines):
    """Return (header range, [(job, job range, header end, [(step label, range)])]) as 0-based half-open ranges."""
    jobs_at = next((i for i, l in enumerate(lines) if re.match(r"^jobs:\s*(#.*)?$", l)), None)
    if jobs_at is None:
        return (0, len(lines)), []
    body = [i for i in range(jobs_at + 1, len(lines)) if lines[i].strip() and not lines[i].lstrip().startswith("#")]
    end_jobs = next((i for i in body if indent(lines[i]) == 0), len(lines))
    body = [i for i in body if i < end_jobs]
    if not body:
        return (0, jobs_at + 1), []
    job_indent = indent(lines[body[0]])
    starts = [i for i in body if indent(lines[i]) == job_indent and KEY.match(lines[i])]
    jobs = []
    for a, b in zip(starts, starts[1:] + [end_jobs]):
        name = KEY.match(lines[a]).group(2)
        steps_at = next((i for i in range(a + 1, b) if re.match(r"^\s+steps:\s*$", lines[i])), None)
        steps = []
        if steps_at is not None:
            dash = [i for i in range(steps_at + 1, b) if lines[i].lstrip().startswith("- ")]
            if dash:
                step_indent = indent(lines[dash[0]])
                sstarts = [i for i in dash if indent(lines[i]) == step_indent]
                for k, (s, e) in enumerate(zip(sstarts, sstarts[1:] + [b])):
                    label = next((m.group(1) for l in lines[s:e] if (m := re.match(r"^\s*-?\s*(?:name|uses|run):\s*(.+)$", l))), "")
                    steps.append((f"steps[{k}] {label}".strip(), (s, e)))
        jobs.append((name, (a, b), steps_at + 1 if steps_at is not None else b, steps))
    return (0, jobs_at + 1), jobs


def ci_unit(path, inventory):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    (ha, hb), jobs = ci_structure(lines)

    def item(where, a, b, kind):
        while b > a and not lines[b - 1].strip():
            b -= 1
        return {"path": where, "kind": kind, "start": a + 1, "end": b, "text": "\n".join(lines[a:b])}

    items = [item("workflow header", ha, hb, "header")]
    for name, (a, b), header_end, steps in jobs:
        items.append(item(f"jobs.{name}", a, header_end, "job"))
        items += [item(f"jobs.{name}.{label}", s, e, "step") for label, (s, e) in steps]
    context = cap("This workflow's header:\n" + "\n".join(lines[ha:hb]) + "\n\nAll reviewed jobs:\n" + inventory, CI_INVENTORY_BYTES + CONTEXT_BYTES)
    return {"id": Path(path).name, "title": Path(path).name, "source": str(path), "context": context, "items": items}


SETUP_STEP = re.compile(r"^(actions/(checkout|cache|setup-[\w-]+|upload-artifact|download-artifact)|[\w-]+/[\w-]*toolchain)@")


def ci_inventory(paths):
    """One line per job: workflow, job id and its non-setup steps."""
    rows = []
    for path in paths:
        _, jobs = ci_structure(Path(path).read_text(encoding="utf-8").splitlines())
        for name, _, _, steps in jobs:
            labels = [label.split(" ", 1)[-1] for label, _ in steps]
            rows.append(f"{Path(path).name} {name}: " + "; ".join(l for l in labels if not SETUP_STEP.match(l)))
    return "\n".join(rows)


# ---------- requests ----------

def build_request(situation, unit, items):
    spec = SITUATIONS[situation]
    state = {"rules": spec["rules"], "situation": situation,
             "unit": {"id": unit["id"], "title": unit["title"], "source": unit["source"]},
             "context": unit["context"],
             "caller_context": unit.get("caller_context", ""),
             "items": {i["qid"]: {"where": f"{i['path']} (lines {i['start']}-{i['end']})", "text": i["text"]} for i in items}}
    questions = {i["qid"]: {"type": "choice", "instructions": spec["instructions"].format(id=i["qid"]), "criteria": spec["criteria"]}
                 for i in items}
    return {"model": MODEL, "state": state, "questions": questions}


def encode(request):
    return json.dumps(request, allow_nan=False).encode("utf-8")


def split_item(item):
    lines = item["text"].splitlines()
    if len(lines) < 2:
        raise JevError("JEV.INCONCLUSIVE", f"A single line at {item['path']} line {item['start']} exceeds {MAX_REQUEST_BYTES} bytes; split it by hand without dropping content")
    half = len(lines) // 2
    head = dict(item, qid=item["qid"] + "a", end=item["start"] + half - 1, text="\n".join(lines[:half]))
    tail = dict(item, qid=item["qid"] + "b", start=item["start"] + half, text="\n".join(lines[half:]))
    return [head, tail]


def batches(situation, unit, limit=MAX_REQUEST_BYTES, max_questions=MAX_QUESTIONS):
    """Pack the unit's items into requests; oversize items are split on lines, nothing is dropped."""
    pending = [dict(i, qid=f"i{n}") for n, i in enumerate(unit["items"], 1)]
    out, cur = [], []
    while pending:
        item = pending.pop(0)
        if len(cur) < max_questions and len(encode(build_request(situation, unit, cur + [item]))) <= limit:
            cur.append(item)
            continue
        if cur:
            out.append(cur)
            cur = []
        if len(encode(build_request(situation, unit, [item]))) <= limit:
            cur = [item]
        else:
            pending[:0] = split_item(item)
    if cur:
        out.append(cur)
    return out


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
        problem = answer_problem(answer, options)
        if problem:
            raise JevError("JEV.RESPONSE_INVALID", f"Invalid Choice answer for {qid}: {problem}")
    return value


def answer_problem(answer, options):
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return "not a choice answer"
    if answer.get("choice") not in options:
        return f"choice {answer.get('choice')!r} is not an option"
    if not probability(answer.get("confidence")):
        return "confidence is not a probability"
    probs = answer.get("probabilities")
    if not isinstance(probs, dict) or set(probs) != options:
        return "probability keys differ from the options"
    if not all(probability(p) for p in probs.values()):
        return "a probability is out of range"
    total = sum(probs.values())
    if abs(total - 1) > ROUNDING * len(options):  # Jev rounds each probability to two decimals.
        return f"probabilities sum to {total:.4f}"
    return None


def api_key():
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise JevError("JEV.UNAVAILABLE", "TYPESAFE_API_KEY is missing; no Jev evaluation ran", True)
    if not key.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in key):
        raise JevError("JEV.UNAVAILABLE", "TYPESAFE_API_KEY has invalid formatting")
    return key


def post(body, key):
    for attempt in range(2):
        conn = http.client.HTTPSConnection(HOST, timeout=60)
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


# ---------- report ----------

def classify(situation, probs):
    """Normalize, then sum probability into clear, pattern and insufficient groups."""
    clear, total = SITUATIONS[situation]["clear"], sum(probs.values()) or 1
    norm = {o: p / total for o, p in probs.items()}
    patterns = {o: p for o, p in norm.items() if o not in clear and o != "insufficient"}
    return {"clear": sum(norm[o] for o in clear), "pattern": sum(patterns.values()),
            "insufficient": norm.get("insufficient", 0.0), "patterns": patterns}


def review_unit(situation, unit, key, transport=post, minimum_probability=0.8):
    """Findings: pattern probability at or above the minimum. Uncertain: neither clear nor pattern reached it."""
    report = {"unit": unit["id"], "source": unit["source"], "findings": [], "uncertain": [], "clear": 0}
    for batch in batches(situation, unit):
        answers = evaluate(build_request(situation, unit, batch), key, transport)["answers"]
        for item in batch:
            groups = classify(situation, answers[item["qid"]]["probabilities"])
            if groups["clear"] >= minimum_probability:
                report["clear"] += 1
                continue
            ranked = sorted(((p, o) for o, p in groups["patterns"].items() if p >= 0.05), reverse=True)
            entry = {"item": item["qid"], "where": item["path"], "lines": [item["start"], item["end"]],
                     "pattern": ranked[0][1] if ranked else None, "pattern_probability": round(groups["pattern"], 2),
                     "patterns": {o: round(p, 2) for p, o in ranked}, "text": item["text"]}
            if "field" in item:
                entry["field"] = item["field"]
            if groups["pattern"] >= minimum_probability:
                report["findings"].append(entry)
            else:
                entry["clear_probability"] = round(groups["clear"], 2)
                entry["insufficient_probability"] = round(groups["insufficient"], 2)
                report["uncertain"].append(entry)
    return report


def load_caller_context(path):
    if path is None:
        return ""
    text = Path(path).read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > CALLER_CONTEXT_BYTES:
        raise JevError("JEV.INCONCLUSIVE", f"Caller context exceeds {CALLER_CONTEXT_BYTES} bytes; keep facts that name items, drop the rest")
    return text


def load_units(args):
    caller_context = load_caller_context(args.context)
    units = collect_units(args)
    for unit in units:
        unit["caller_context"] = caller_context
    return units


def collect_units(args):
    if args.situation == "ci":
        inventory = cap(ci_inventory(args.inputs), CI_INVENTORY_BYTES)
        return [ci_unit(p, inventory) for p in args.inputs]
    if args.beads_json:
        if args.situation != "plan" or args.inputs:
            raise JevError("VALIDATION.INPUT", "--beads-json applies to the plan situation and replaces the input paths")
        return [plan_unit_from_bead(b) for b in load_beads(args.beads_json)]
    if not args.inputs:
        raise JevError("VALIDATION.INPUT", "No inputs given")
    return [u for p in args.inputs for u in md_units(p, args.situation, args.sprint_level)]


SUGGESTED = {
    "JEV.UNAVAILABLE": "Set TYPESAFE_API_KEY or restore network access, then rerun",
    "JEV.RESPONSE_INVALID": "Rerun once; if it repeats, report the message to the skill owner",
    "JEV.INCONCLUSIVE": "Shrink the named item or the context file without dropping checks, then rerun",
    "VALIDATION.INPUT": "Check the input paths or the bead JSON shape (references/plan-beads.md), then rerun",
}


def failure(code, message, recoverable):
    return {"success": False, "data": None, "error": {
        "code": code, "message": message, "recoverable": recoverable, "suggested_action": SUGGESTED[code]}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("situation", choices=sorted(SITUATIONS))
    parser.add_argument("inputs", nargs="*",
                        help="plan: sprint md files; ci: workflow files; instructions: CLAUDE.md, AGENTS.md, SKILL.md or agent prompt files")
    parser.add_argument("--beads-json", metavar="FILE", help="plan: bead JSON from `bd show --json` or `br show --json`, a file or - for stdin")
    parser.add_argument("--sprint-level", type=int, help="plan md: each heading at this level starts a sprint (default: one sprint per file)")
    parser.add_argument("--context", type=Path, help=f"caller-collected context file (at most {CALLER_CONTEXT_BYTES} bytes), sent with every request")
    parser.add_argument("--minimum-probability", type=float, default=0.8)
    parser.add_argument("--dry-run", action="store_true", help="print units, item counts and request sizes; no Jev call")
    parser.add_argument("--brief", type=int, metavar="CHARS", help="truncate each reported item's text to CHARS characters")
    args = parser.parse_args(argv)
    try:
        units = load_units(args)
        if args.dry_run:
            data = {"units": [{"unit": u["id"], "items": len(u["items"]),
                               "requests": [len(encode(build_request(args.situation, u, b))) for b in batches(args.situation, u)]}
                              for u in units]}
        else:
            key = api_key()
            reports = [review_unit(args.situation, u, key, minimum_probability=args.minimum_probability) for u in units]
            totals = {k: sum(len(r[k]) for r in reports) for k in ("findings", "uncertain")}
            totals["clear"] = sum(r["clear"] for r in reports)
            if args.brief:
                for entry in (e for r in reports for k in ("findings", "uncertain") for e in r[k]):
                    if len(entry["text"]) > args.brief:
                        entry["text"] = entry["text"][:args.brief] + "…"
            data = {"situation": args.situation, "units": reports, "totals": totals}
        result = {"success": True, "data": data, "error": None}
    except JevError as exc:
        result = failure(exc.code, exc.message, exc.recoverable)
    except (OSError, UnicodeError, ValueError):
        result = failure("VALIDATION.INPUT", "Input unavailable or unreadable", False)
    print(json.dumps(result, indent=2, allow_nan=False))
    if not result["success"]:
        return 2
    totals = result["data"].get("totals", {})
    return 1 if totals.get("findings") else 0


if __name__ == "__main__":
    sys.exit(main())
