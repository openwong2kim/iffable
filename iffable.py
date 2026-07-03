#!/usr/bin/env python3
"""iffable — Claude Code 쿼터 보존 가드 (오리지널 구현).

Fable 5(최상위 모델)로 시작한 세션에서만 무장(arm)하여,
세션 시작 시 오케스트레이션 정책을 주입하고,
(a) Haiku 서브에이전트 스폰, (b) 레저 없는 대형 위임, (c) 열린 레저 항목이
남은 채로 턴 종료 — 세 가지를 기계적으로 차단한다.

CLI: `python3 iffable.py <subcommand>` (stdin으로 JSON 페이로드).
서브커맨드: session-start / guard-spawn / guard-stop / session-end.

원칙: 모든 서브커맨드는 try/except로 감싸 잘못된 입력에서도 조용히 exit 0
(fail-open — 깨진 훅이 세션을 절대 망가뜨려선 안 된다).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from typing import Any, Dict, Optional, Tuple

# ── 상수 ──────────────────────────────────────────────────────────────────
# IFFABLE_HOME 미설정 시 기본 위치
DEFAULT_HOME = os.path.expanduser("~/.claude/iffable")
# 스폰 프롬프트 기본 상한(자) — 초과 && 레저 부재 시 deny
DEFAULT_SPAWN_LIMIT = 1500
# 유효 프로파일 값
VALID_PROFILES = ("fable", "fallback", "off")


# ── 유틸 ──────────────────────────────────────────────────────────────────
def _sanitize_session_id(session_id: str) -> str:
    """세션 ID를 파일명 안전 문자(alnum/-/_)만 남기도록 정리한다."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id))[:128]


def _cache_path(session_id: str) -> str:
    """세션별 캐시 파일 경로를 반환한다."""
    safe = _sanitize_session_id(session_id)
    return os.path.join(tempfile.gettempdir(), f"iffable-{safe}.json")


def _home_dir() -> str:
    """IFFABLE_HOME 환경변수(없으면 기본값)를 반환한다."""
    return os.environ.get("IFFABLE_HOME") or DEFAULT_HOME


def _spawn_limit() -> int:
    """IFFABLE_SPAWN_LIMIT 환경변수(정수, 없으면 기본값)를 반환한다."""
    raw = os.environ.get("IFFABLE_SPAWN_LIMIT")
    if raw is None:
        return DEFAULT_SPAWN_LIMIT
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SPAWN_LIMIT


def _env_profile_override() -> Optional[str]:
    """IFFABLE_PROFILE 환경변수가 유효한 강제 프로파일이면 반환, 아니면 None.

    'auto'(또는 미설정/무효값)는 자동 판별을 의미하므로 None을 돌려준다.
    """
    raw = os.environ.get("IFFABLE_PROFILE")
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in VALID_PROFILES:
        return value
    return None


# ── 프로파일 해석 ──────────────────────────────────────────────────────────
def resolve_profile(model: Optional[str]) -> str:
    """모델 문자열로부터 프로파일을 해석한다.

    - env IFFABLE_PROFILE 이 fable/fallback/off 면 그 값이 우선.
    - 아니면 auto: model 에 'fable' 포함(대소문자 무관) → 'fable', 그 외 → 'fallback'.
    """
    override = _env_profile_override()
    if override is not None:
        return override
    if model and "fable" in model.lower():
        return "fable"
    return "fallback"


def profile_from_cache(session_id: str) -> str:
    """세션 캐시에서 프로파일을 읽는다.

    env 오버라이드가 있으면 항상 우선. 캐시가 없거나 깨졌으면 'fallback'.
    """
    override = _env_profile_override()
    if override is not None:
        return override
    try:
        with open(_cache_path(session_id), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        profile = data.get("profile")
        if profile in VALID_PROFILES:
            return profile
    except (OSError, ValueError):
        pass
    return "fallback"


# ── 레저 탐색 ──────────────────────────────────────────────────────────────
def find_ledger(start_dir: str) -> Optional[str]:
    """start_dir 에서 부모로 올라가며 `.workflow/LEDGER.md` 를 찾는다.

    각 디렉터리에서 레저를 먼저 확인하고, 없으면 `.git`(파일일 수도 있음 —
    worktree) 존재 시 그 디렉터리를 경계로 탐색을 멈춘다. 파일시스템 루트에
    도달하면 종료. 찾으면 절대 경로, 못 찾으면 None.
    """
    if not start_dir:
        return None
    current = os.path.abspath(start_dir)
    while True:
        ledger = os.path.join(current, ".workflow", "LEDGER.md")
        if os.path.isfile(ledger):
            return ledger
        # .git 경계(디렉터리 또는 worktree의 파일)에서 멈춘다.
        if os.path.exists(os.path.join(current, ".git")):
            return None
        parent = os.path.dirname(current)
        if parent == current:  # 루트 도달
            return None
        current = parent


def ledger_open_items(ledger_path: str) -> list:
    """레저에서 열린 항목(`- [ ]` 로 시작하는 줄)들을 리스트로 반환한다."""
    items = []
    try:
        with open(ledger_path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.lstrip().startswith("- [ ]"):
                    items.append(line.rstrip("\n"))
    except OSError:
        pass
    return items


# ── 판정 로직(순수 함수 — 테스트 대상) ──────────────────────────────────────
def decide_spawn(
    profile: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    cwd: str,
    limit: int,
) -> Optional[str]:
    """스폰 가드 판정. deny 사유 문자열을 반환하거나, 허용이면 None.

    - HAIKU 금지: 모든 프로파일에서 tool_input.model 에 'haiku' 포함 시 deny.
    - 레저 가드: fable 프로파일에서만. fork 는 면제. 텍스트 길이 > limit 이고
      레저 부재 시 deny.
    """
    if not isinstance(tool_input, dict):
        tool_input = {}

    # (1) Haiku 금지 — 프로파일 무관, 항상 적용
    model = tool_input.get("model")
    if isinstance(model, str) and "haiku" in model.lower():
        return (
            "Haiku 계열 서브에이전트는 정책상 금지되어 있습니다(품질 하한). "
            "간단한 작업이라면 claude-sonnet-4-6 로 스폰하세요. "
            "Haiku subagents are banned by iffable policy — use claude-sonnet-4-6 "
            "for simple work instead."
        )

    # (2) 레저 가드 — fable 프로파일에서만
    if profile != "fable":
        return None

    # fork 는 대화 컨텍스트를 상속하므로 레저 요구에서 면제
    if tool_input.get("subagent_type") == "fork":
        return None

    if tool_name == "Workflow":
        text = tool_input.get("script")
    else:
        text = tool_input.get("prompt")
    text = text if isinstance(text, str) else ""

    if len(text) > limit and find_ledger(cwd) is None:
        return (
            "대형 위임({} > {}자)인데 Requirements Ledger 가 없습니다. "
            "먼저 ./.workflow/LEDGER.md 에 번호가 매겨진 체크박스 레저 "
            "(`- [ ] N. <항목>`)를 작성한 뒤, 레저 항목을 인용해 다시 스폰하세요. "
            "정말로 사소한 작업이면 위임하지 말고 직접 수행하세요. "
            "This delegation exceeds the spawn limit without a ledger — write "
            "./.workflow/LEDGER.md first, then re-spawn citing its items."
        ).format(len(text), limit)

    return None


def decide_stop(
    profile: str,
    cwd: str,
    stop_hook_active: Any,
) -> Optional[str]:
    """Stop 가드 판정. block 사유 문자열을 반환하거나, 허용이면 None.

    - stop_hook_active 참 → 허용(무한루프 방지, 최대 1회만 차단).
    - profile != fable → 허용. 레저 없음 → 허용.
    - 레저에 열린 `- [ ]` 항목 존재 → block(항목 나열 + 지시).
    """
    if stop_hook_active:
        return None
    if profile != "fable":
        return None

    ledger = find_ledger(cwd)
    if ledger is None:
        return None

    open_items = ledger_open_items(ledger)
    if not open_items:
        return None

    shown = open_items[:10]
    more = len(open_items) - len(shown)
    lines = "\n".join(shown)
    suffix = f"\n… (+{more} more)" if more > 0 else ""
    return (
        "Requirements Ledger 에 열린 항목이 남아 턴을 종료할 수 없습니다:\n"
        f"{lines}{suffix}\n\n"
        "각 항목을 끝내고 검증되면 `- [x]` 로, 사용자 승인 하에 보류하면 "
        "`- [~] deferred: <사유>` 로 표시한 뒤 종료하세요. "
        "(Finish these items, mark `- [x]` when verified, or `- [~] deferred: "
        "<reason>` with user approval.)"
    )


# ── 서브커맨드 핸들러 ───────────────────────────────────────────────────────
def _read_payload() -> Dict[str, Any]:
    """stdin 에서 JSON 페이로드를 읽는다(비었으면 빈 dict)."""
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def cmd_session_start(payload: Dict[str, Any]) -> None:
    """세션 시작: 프로파일 해석 → 캐시 기록 → instructions 주입."""
    session_id = str(payload.get("session_id", ""))
    model = payload.get("model")
    profile = resolve_profile(model if isinstance(model, str) else None)

    # 세션별 캐시 기록(profile 미상시 이후 가드가 참조)
    if session_id:
        try:
            with open(_cache_path(session_id), "w", encoding="utf-8") as fh:
                json.dump(
                    {"model": model, "profile": profile, "session_id": session_id},
                    fh,
                )
        except OSError:
            pass  # 캐시 실패도 세션을 막지 않는다

    if profile == "off":
        return  # 완전 휴면 — 아무것도 출력하지 않음

    filename = (
        "orchestrator-fable.md" if profile == "fable" else "orchestrator-fallback.md"
    )
    instr_path = os.path.join(_home_dir(), "instructions", filename)
    try:
        with open(instr_path, "r", encoding="utf-8") as fh:
            context = fh.read()
    except OSError:
        return  # instructions 파일이 없으면 주입 생략(fail-open)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(out))


def cmd_guard_spawn(payload: Dict[str, Any]) -> None:
    """PreToolUse(Agent|Task|Workflow): Haiku 금지 + 레저 가드."""
    session_id = str(payload.get("session_id", ""))
    profile = profile_from_cache(session_id)
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd", "")

    reason = decide_spawn(profile, tool_name, tool_input, cwd, _spawn_limit())
    if reason is None:
        return  # 허용 — 아무것도 출력하지 않음

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))


def cmd_guard_stop(payload: Dict[str, Any]) -> None:
    """Stop: 열린 레저 항목이 있으면 턴 종료 차단."""
    session_id = str(payload.get("session_id", ""))
    profile = profile_from_cache(session_id)
    cwd = payload.get("cwd", "")
    stop_hook_active = payload.get("stop_hook_active", False)

    reason = decide_stop(profile, cwd, stop_hook_active)
    if reason is None:
        return  # 허용

    print(json.dumps({"decision": "block", "reason": reason}))


def cmd_session_end(payload: Dict[str, Any]) -> None:
    """세션 종료: 캐시 파일 삭제(에러 무시)."""
    session_id = str(payload.get("session_id", ""))
    if not session_id:
        return
    try:
        os.remove(_cache_path(session_id))
    except OSError:
        pass


# ── 엔트리포인트 ────────────────────────────────────────────────────────────
_HANDLERS = {
    "session-start": cmd_session_start,
    "guard-spawn": cmd_guard_spawn,
    "guard-stop": cmd_guard_stop,
    "session-end": cmd_session_end,
}


def main(argv: Optional[list] = None) -> int:
    """CLI 엔트리포인트. 어떤 예외에서도 exit 0(fail-open)."""
    argv = sys.argv[1:] if argv is None else argv
    try:
        if not argv:
            return 0
        handler = _HANDLERS.get(argv[0])
        if handler is None:
            return 0
        payload = _read_payload()
        handler(payload)
    except Exception:
        # 어떤 이유로든 실패해도 세션을 막지 않는다. stderr 로도 새지 않음.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
