"""iffable 핵심 함수 단위 테스트 (unittest, 외부 의존성 0).

실행: `python3 -m unittest discover -s tests`
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

# 레포 루트를 import 경로에 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import iffable  # noqa: E402


def _clear_env() -> None:
    """관련 환경변수를 초기화한다(테스트 격리)."""
    for key in ("IFFABLE_PROFILE", "IFFABLE_HOME", "IFFABLE_SPAWN_LIMIT"):
        os.environ.pop(key, None)


class TestProfileResolution(unittest.TestCase):
    def setUp(self) -> None:
        _clear_env()

    def tearDown(self) -> None:
        _clear_env()

    def test_fable_model_auto(self) -> None:
        self.assertEqual(iffable.resolve_profile("claude-fable-5"), "fable")
        self.assertEqual(iffable.resolve_profile("Claude-FABLE-5"), "fable")

    def test_non_fable_model_auto(self) -> None:
        self.assertEqual(iffable.resolve_profile("claude-opus-4-8"), "fallback")
        self.assertEqual(iffable.resolve_profile(None), "fallback")
        self.assertEqual(iffable.resolve_profile(""), "fallback")

    def test_env_override_wins(self) -> None:
        os.environ["IFFABLE_PROFILE"] = "off"
        self.assertEqual(iffable.resolve_profile("claude-fable-5"), "off")
        os.environ["IFFABLE_PROFILE"] = "fable"
        self.assertEqual(iffable.resolve_profile("claude-opus-4-8"), "fable")
        os.environ["IFFABLE_PROFILE"] = "fallback"
        self.assertEqual(iffable.resolve_profile("claude-fable-5"), "fallback")

    def test_env_auto_or_invalid_ignored(self) -> None:
        os.environ["IFFABLE_PROFILE"] = "auto"
        self.assertEqual(iffable.resolve_profile("claude-fable-5"), "fable")
        os.environ["IFFABLE_PROFILE"] = "garbage"
        self.assertEqual(iffable.resolve_profile("claude-opus-4-8"), "fallback")


class TestLedgerWalkUp(unittest.TestCase):
    def setUp(self) -> None:
        _clear_env()

    def tearDown(self) -> None:
        _clear_env()

    def test_found_in_parent(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            wf = os.path.join(root, ".workflow")
            os.makedirs(wf)
            ledger = os.path.join(wf, "LEDGER.md")
            with open(ledger, "w") as fh:
                fh.write("- [ ] 1. do it\n")
            deep = os.path.join(root, "a", "b", "c")
            os.makedirs(deep)
            found = iffable.find_ledger(deep)
            self.assertIsNotNone(found)
            self.assertEqual(os.path.realpath(found), os.path.realpath(ledger))

    def test_stopped_by_git_boundary(self) -> None:
        # root/.workflow/LEDGER.md 는 존재하지만 sub 에 .git 경계가 있어
        # sub 에서 시작하면 root 로 올라가지 못한다.
        with tempfile.TemporaryDirectory() as root:
            wf = os.path.join(root, ".workflow")
            os.makedirs(wf)
            with open(os.path.join(wf, "LEDGER.md"), "w") as fh:
                fh.write("- [ ] 1. x\n")
            sub = os.path.join(root, "repo")
            os.makedirs(sub)
            # .git 을 파일로 생성(worktree 케이스) — 경계로 인식되어야 함
            with open(os.path.join(sub, ".git"), "w") as fh:
                fh.write("gitdir: /elsewhere\n")
            self.assertIsNone(iffable.find_ledger(sub))

    def test_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            deep = os.path.join(root, "x", "y")
            os.makedirs(deep)
            self.assertIsNone(iffable.find_ledger(deep))

    def test_open_items_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            ledger = os.path.join(root, "L.md")
            with open(ledger, "w") as fh:
                fh.write(
                    "# title\n"
                    "- [ ] 1. open one\n"
                    "- [x] 2. done\n"
                    "- [~] 3. deferred: later\n"
                    "  - [ ] 4. indented open\n"
                )
            items = iffable.ledger_open_items(ledger)
            self.assertEqual(len(items), 2)  # 1번 + 들여쓴 4번


class TestSpawnGuard(unittest.TestCase):
    def setUp(self) -> None:
        _clear_env()

    def tearDown(self) -> None:
        _clear_env()

    def test_haiku_deny_on_fable(self) -> None:
        reason = iffable.decide_spawn(
            "fable", "Agent", {"model": "claude-haiku-4-5", "prompt": "hi"}, "/tmp", 1500
        )
        self.assertIsNotNone(reason)
        self.assertIn("Haiku", reason)

    def test_haiku_deny_on_fallback(self) -> None:
        # Haiku 는 프로파일 무관하게 항상 차단
        reason = iffable.decide_spawn(
            "fallback", "Agent", {"model": "CLAUDE-HAIKU-4-5"}, "/tmp", 1500
        )
        self.assertIsNotNone(reason)

    def test_large_prompt_no_ledger_denies_on_fable(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".git"))  # 레저 없는 경계
            big = "x" * 1600
            reason = iffable.decide_spawn(
                "fable", "Agent", {"prompt": big}, root, 1500
            )
            self.assertIsNotNone(reason)
            self.assertIn("LEDGER", reason)

    def test_large_prompt_with_ledger_allows(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".workflow"))
            with open(os.path.join(root, ".workflow", "LEDGER.md"), "w") as fh:
                fh.write("- [ ] 1. x\n")
            big = "x" * 1600
            reason = iffable.decide_spawn(
                "fable", "Agent", {"prompt": big}, root, 1500
            )
            self.assertIsNone(reason)

    def test_small_prompt_allows(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".git"))
            reason = iffable.decide_spawn(
                "fable", "Agent", {"prompt": "small"}, root, 1500
            )
            self.assertIsNone(reason)

    def test_fork_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".git"))
            big = "x" * 1600
            reason = iffable.decide_spawn(
                "fable",
                "Agent",
                {"prompt": big, "subagent_type": "fork"},
                root,
                1500,
            )
            self.assertIsNone(reason)

    def test_fallback_profile_dormant_for_large(self) -> None:
        # fallback 프로파일에서는 대형 스폰도 레저 가드 미적용(Haiku만 차단)
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".git"))
            big = "x" * 1600
            reason = iffable.decide_spawn(
                "fallback", "Agent", {"prompt": big}, root, 1500
            )
            self.assertIsNone(reason)

    def test_workflow_uses_script_field(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".git"))
            big = "x" * 1600
            reason = iffable.decide_spawn(
                "fable", "Workflow", {"script": big}, root, 1500
            )
            self.assertIsNotNone(reason)


class TestStopGuard(unittest.TestCase):
    def setUp(self) -> None:
        _clear_env()

    def tearDown(self) -> None:
        _clear_env()

    def _make_ledger(self, root: str, content: str) -> None:
        os.makedirs(os.path.join(root, ".workflow"))
        with open(os.path.join(root, ".workflow", "LEDGER.md"), "w") as fh:
            fh.write(content)

    def test_open_item_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self._make_ledger(root, "- [ ] 1. still open\n- [x] 2. done\n")
            reason = iffable.decide_stop("fable", root, False)
            self.assertIsNotNone(reason)
            self.assertIn("still open", reason)

    def test_all_closed_allows(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self._make_ledger(root, "- [x] 1. done\n- [~] 2. deferred: ok\n")
            self.assertIsNone(iffable.decide_stop("fable", root, False))

    def test_stop_hook_active_allows(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self._make_ledger(root, "- [ ] 1. open\n")
            self.assertIsNone(iffable.decide_stop("fable", root, True))

    def test_non_fable_allows(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self._make_ledger(root, "- [ ] 1. open\n")
            self.assertIsNone(iffable.decide_stop("fallback", root, False))

    def test_no_ledger_allows(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(iffable.decide_stop("fable", root, False))


class TestCacheProfile(unittest.TestCase):
    def setUp(self) -> None:
        _clear_env()

    def tearDown(self) -> None:
        _clear_env()

    def test_cache_roundtrip(self) -> None:
        sid = "unittest-cache-xyz"
        try:
            iffable.cmd_session_start({"session_id": sid, "model": "claude-fable-5"})
            self.assertEqual(iffable.profile_from_cache(sid), "fable")
        finally:
            try:
                os.remove(iffable._cache_path(sid))
            except OSError:
                pass

    def test_missing_cache_is_fallback(self) -> None:
        self.assertEqual(
            iffable.profile_from_cache("no-such-session-id-12345"), "fallback"
        )

    def test_env_override_beats_cache(self) -> None:
        os.environ["IFFABLE_PROFILE"] = "off"
        self.assertEqual(iffable.profile_from_cache("anything"), "off")


if __name__ == "__main__":
    unittest.main()
