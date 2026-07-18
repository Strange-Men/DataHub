"""M9.3 frontend governance workflow and safety contracts."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"


def _read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def test_role_is_loaded_only_from_authenticated_backend_principal() -> None:
    context = _read("auth/AuthContext.tsx")
    controls = _read("components/AuthControls.tsx")
    assert 'apiPath("/api/auth/me")' in context
    assert "isAuthRole(resolvedRole)" in context
    assert "setRole(resolvedRole)" in context
    assert "ROLE_LABELS[role]" in controls
    assert "setRole" not in controls
    assert "localStorage" not in context + controls


def test_clearing_token_clears_role_and_future_authorization_header() -> None:
    context = _read("auth/AuthContext.tsx")
    api = _read("api.ts")
    assert "clearAuthSession();" in context
    assert "setRole(null);" in context
    assert ".removeItem(AUTH_TOKEN_KEY)" in api
    assert "if (token && !headers.has(\"Authorization\"))" in api


def test_frontend_permission_matrix_covers_all_five_roles() -> None:
    governance = _read("governance.ts")
    for role in ("admin", "cleaner", "reviewer", "service", "viewer"):
        assert f"{role}: new Set(" in governance
    assert '"p2.serve"' in governance
    assert '"retrieval.unified"' in governance
    assert "当前角色没有执行此操作的权限。" in governance


def test_p2_workflow_uses_real_contracts_and_visibility_gates() -> None:
    page = _read("pages/P2MaterialCenter.tsx")
    workflow = _read("components/P2WorkflowHeader.tsx")
    for fragment in (
        "/extract`",
        "/embed`",
        "/serve`",
        "/archive`",
        "发起内容解析",
        "知识向量已经生成",
        "已开放检索",
        "知识资产 → 知识快照 → 人工审核 → 内容解析 → 原始素材",
    ):
        assert fragment in page
    for stage in (
        "素材上传与解析",
        "内容修订与审核",
        "知识快照与发布",
        "索引构建与开放检索",
        "检索验证与归档",
    ):
        assert stage in workflow
    assert "repeat(5" not in page
    assert "window.confirm" in page
    assert "embedding_vector" not in page


def test_retrieval_validation_keeps_unified_and_agent_opt_in_explicit() -> None:
    page = _read("pages/RetrievalValidation.tsx")
    assert 'retrieval_strategy: agentUnified ? "unified" : "p1"' in page
    assert "shadow_mode: !activeUnified" in page
    assert "include_archived: false" in page
    assert "客服 Agent 保持默认 P1-only" in page
    assert "/api/v2/retrieval/p2/search" in page
    assert "/api/v2/retrieval/search" in page
    assert "/api/v2/customer-ops-agent/retrieve" in page


def test_errors_confirmations_and_loading_are_user_safe() -> None:
    governance = _read("governance.ts")
    p1 = _read("pages/P1TextHub.tsx")
    p2 = _read("pages/P2MaterialCenter.tsx")
    retrieval = _read("pages/RetrievalValidation.tsx")
    for status_text in ("身份验证失败", "当前角色没有", "对象不存在", "状态不允许", "输入内容不合法", "暂不可用"):
        assert status_text in governance
    assert "RAG 同步会改变 Agent 可检索的知识范围" in p1
    assert "归档后该知识将立即停止被检索" in p2
    assert "检索中，请勿重复提交" in retrieval
    assert "console.log" not in governance + p1 + p2 + retrieval


def test_home_exposes_real_modules_and_disables_p3_p4() -> None:
    home = _read("pages/HomePage.tsx")
    layout = _read("components/Layout.tsx")
    styles = _read("styles.css")
    assert 'path: "/p2-material-center"' in home
    assert 'path: "/retrieval-validation"' in home
    assert home.count('status: "规划中"') == 2
    assert "capability-mark" in home
    assert "💬" not in home and "🎨" not in home and "🔎" not in home
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in styles
    assert "P1 文本知识治理" in layout
    assert "P2 多模态知识治理" in layout
    assert "检索与 Agent 验证" in home + layout


def test_retrieval_uses_compact_explicit_mode_switch() -> None:
    page = _read("pages/RetrievalValidation.tsx")
    switch = _read("components/ModeSwitch.tsx")
    styles = _read("styles.css")
    assert "使用联合检索结果" in page
    assert "仅观察 P1/P2 联合召回，不影响最终结果。" in page
    assert 'role="switch"' in switch
    assert "aria-checked={checked}" in switch
    assert "compact-switch" in switch + styles
    assert "width: 44px" in styles
    assert 'type="checkbox"' not in page


def test_no_token_or_secret_is_written_to_url_or_console() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in SRC.rglob("*.tsx"))
    api = _read("api.ts")
    assert "Authorization" in api
    assert "Bearer ${token}" in api
    assert "?token=" not in sources + api
    assert "console.log" not in sources + api
