from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_API = REPO_ROOT / "frontend" / "src" / "api.ts"


def test_frontend_user_routes_use_backend_api_base() -> None:
    source = FRONTEND_API.read_text()

    assert "export const BACKEND_API_BASE = import.meta.env.VITE_BACKEND_URL || '/api/data'" in source
    assert "headers.set('x-user-id', getLocalUserId())" in source
    assert "getUserProfile: () => fetchBackendJSON<SavedSettings>('/user/profile', withLocalUserId())," in source
    assert "fetchBackendJSON<UserQuery[]>(`/user/queries?limit=${limit}`, withLocalUserId())," in source
    assert "fetchBackendJSON<UserQuery>('/user/queries', withLocalUserId({" in source
    assert "return fetchJSON<UserMemoryData>(`/user/memories?user_id=${encodeURIComponent(userId)}`)" in source
