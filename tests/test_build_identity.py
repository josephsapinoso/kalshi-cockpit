"""`/api/health` must be able to say which build is answering it.

**What this establishes:** that a single unauthenticated GET pins the deployed
build to a Fly release, and that every field goes to `None` rather than to a
placeholder when the platform did not supply it.

**What it does not establish:** that the reported build is the one anybody
intended. This is an identity, not a verification -- comparing it against
`git rev-parse HEAD` is still a human (or caller) step.

Why it exists: establishing that commit `999857f` was absent from both deployed
images took a subagent 32 tool calls of behavioural HTML diffing, and the repo
has previously asserted "deployed and verified" and been wrong -- the 52.00% fee
copy served live for three days after the correction landed in git.

The Fly environment was enumerated on a real machine rather than assumed
(`fly ssh console -a kalshi-cockpit-demo -C "env | grep ^FLY_"`, 2026-08-17):

    FLY_ALLOC_ID  FLY_APP_NAME  FLY_IMAGE_REF  FLY_MACHINE_ID
    FLY_MACHINE_VERSION  FLY_PRIVATE_IP  FLY_PROCESS_GROUP  FLY_REGION
    FLY_SSH  FLY_VM_MEMORY_MB  PRIMARY_REGION

`FLY_RELEASE_VERSION` is **not** among them, and none of the ones that are
carries a commit -- `FLY_IMAGE_REF` ends in a deployment ULID and
`fly releases --json` reports `"Metadata": null` on every release.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig, BuildInfo
from backend.seed_demo import seed_all


FLY_VARS = [
    "FLY_IMAGE_REF",
    "FLY_MACHINE_VERSION",
    "FLY_MACHINE_ID",
    "FLY_REGION",
    "GIT_SHA",
]

# A real one, copied from the running demo machine.
REAL_IMAGE_REF = (
    "registry.fly.io/kalshi-cockpit-demo:deployment-01M07XFC5EWSYQA35JYZZR5PQC"
)
REAL_MACHINE_VERSION = "01M07XGMRWJEBFBQCCBSP65MHK"


@pytest.fixture
def clean_env(monkeypatch):
    """No build identity in the environment -- a laptop, or a forgotten flag."""
    for name in FLY_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("build_identity") / "demo.db"
    seed_all(path)
    return path


@pytest.fixture
def demo_app(demo_db):
    return create_app(AppConfig(instance_mode="demo", db_path=demo_db))


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


class TestUnreadableIsNoneAndNotAPlaceholder:
    """CLAUDE.md: unreadable resolves to `None`, never `0` and never a string.

    The specific failure guarded against is `"unknown"` masquerading as data. A
    caller comparing build identifiers across two instances would find
    `"unknown" == "unknown"` and conclude the two machines match, which is the
    exact wrong answer and is worse than no field at all.
    """

    def test_nothing_in_the_environment_gives_every_field_none(self, clean_env):
        info = BuildInfo.from_env()

        assert info.git_sha is None
        assert info.image_ref is None
        assert info.machine_version is None
        assert info.machine_id is None
        assert info.region is None

    def test_an_empty_variable_is_absent_rather_than_empty_string(self, clean_env):
        """Fly hands a `[env]` key set to "" through as an empty string."""
        clean_env.setenv("FLY_IMAGE_REF", "")
        clean_env.setenv("GIT_SHA", "   ")

        info = BuildInfo.from_env()

        assert info.image_ref is None
        assert info.git_sha is None

    def test_no_field_is_ever_the_string_unknown(self, clean_env):
        assert "unknown" not in {
            str(v).lower() for v in BuildInfo.from_env().as_dict().values()
        }


class TestTheImageRefPinsTheDeploy:
    """The env route yields no commit, so the image ref is the load-bearing one.

    Its deployment ULID appears verbatim as `ImageRef` in
    `fly releases --json`, which maps it to a release version and a timestamp.
    That is the one-GET answer to "which deploy is this machine running?".
    """

    def test_it_reports_the_fly_image_ref_verbatim(self, clean_env):
        clean_env.setenv("FLY_IMAGE_REF", REAL_IMAGE_REF)

        assert BuildInfo.from_env().image_ref == REAL_IMAGE_REF

    def test_it_reports_the_machine_version(self, clean_env):
        clean_env.setenv("FLY_MACHINE_VERSION", REAL_MACHINE_VERSION)

        assert BuildInfo.from_env().machine_version == REAL_MACHINE_VERSION


class TestTheGitShaIsRefusedUnlessItLooksLikeOne:
    """`git_sha` is the field a caller would act on, so it is validated.

    CLAUDE.md: clamp what you trust, refuse what you're validating. A build
    identifier is the thing being validated, so a value that cannot be a commit
    is refused rather than echoed -- a truncated or mangled SHA presented as
    authoritative is the "fake value masquerading as data" this repo forbids.
    Refusal is announced in the log, because silently dropping a set-but-wrong
    value reads identically to never having set it.
    """

    def test_a_full_sha_survives(self, clean_env):
        clean_env.setenv("GIT_SHA", "999857f1c0ffee1234567890abcdef1234567890")

        assert (
            BuildInfo.from_env().git_sha
            == "999857f1c0ffee1234567890abcdef1234567890"
        )

    def test_a_short_sha_survives(self, clean_env):
        clean_env.setenv("GIT_SHA", "999857f")

        assert BuildInfo.from_env().git_sha == "999857f"

    def test_it_is_normalised_to_lower_case(self, clean_env):
        """So a caller may compare it to `git rev-parse HEAD` with `==`."""
        clean_env.setenv("GIT_SHA", "999857F")

        assert BuildInfo.from_env().git_sha == "999857f"

    @pytest.mark.parametrize(
        "raw",
        [
            "999857",  # six chars -- too short to be unambiguous
            "9" * 41,  # longer than a sha1
            "999857g",  # not hex
            "$(git rev-parse HEAD)",  # the shell did not expand
            "HEAD",
            "deployment-01M07XFC5EWSYQA35JYZZR5PQC",  # an image ref, not a sha
        ],
    )
    def test_anything_that_is_not_a_sha_becomes_none(self, clean_env, raw, caplog):
        clean_env.setenv("GIT_SHA", raw)

        with caplog.at_level("ERROR"):
            info = BuildInfo.from_env()

        assert info.git_sha is None
        assert "GIT_SHA" in caplog.text


class TestHealthCarriesIt:
    async def test_health_reports_the_build(self, demo_app, clean_env):
        clean_env.setenv("FLY_IMAGE_REF", REAL_IMAGE_REF)
        clean_env.setenv("FLY_MACHINE_VERSION", REAL_MACHINE_VERSION)
        clean_env.setenv("GIT_SHA", "999857f")

        build = (await get(demo_app, "/api/health")).json()["build"]

        assert build["image_ref"] == REAL_IMAGE_REF
        assert build["machine_version"] == REAL_MACHINE_VERSION
        assert build["git_sha"] == "999857f"

    async def test_the_key_is_present_even_when_nothing_is_known(
        self, demo_app, clean_env
    ):
        """A missing key and a null value are different answers.

        A caller that reads `body["build"]["image_ref"]` must get `None` on a
        laptop, not a `KeyError` it has to special-case -- otherwise the check
        gets written defensively and stops distinguishing "no identity" from
        "route is old and has no build field at all".
        """
        build = (await get(demo_app, "/api/health")).json()["build"]

        assert set(build) == {
            "git_sha",
            "image_ref",
            "machine_version",
            "machine_id",
            "region",
        }
        assert all(v is None for v in build.values())

    async def test_it_is_read_per_request_not_captured_at_boot(
        self, demo_app, clean_env
    ):
        """Same reason as `agent_fleet_configured` on the line above it.

        The question this field is asked is "is the thing I just deployed the
        thing that is running?", and a value captured in `create_app` answers a
        question about the process that built the app object.
        """
        assert (await get(demo_app, "/api/health")).json()["build"]["git_sha"] is None

        clean_env.setenv("GIT_SHA", "abcdef1")

        assert (
            await get(demo_app, "/api/health")
        ).json()["build"]["git_sha"] == "abcdef1"

    async def test_it_carries_no_secret(self, demo_app, clean_env, monkeypatch):
        """`/api/health` is public -- Fly's check reads it unauthenticated.

        Build identity is read from a fixed allow-list of names, so a secret
        cannot arrive here by having been set in the same environment.
        """
        monkeypatch.setenv("APP_AUTH_TOKEN", "sk-not-a-real-token-9xQ2v9LmT4pR7wYzB")
        monkeypatch.setenv("KALSHI_API_KEY", "kalshi-9xQ2v9LmT4pR7wYzB1nK6sHf")

        body = (await get(demo_app, "/api/health")).text

        assert "9xQ2v9LmT4pR7wYzB" not in body
