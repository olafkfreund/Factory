#!/usr/bin/env bash
# /run-aws-demo — self-contained PARR deploy-then-verify demo.
# Scaffolds 2 FastAPI services, deploys them to REAL AWS App Runner via
# deterministic Terraform, proves the live API, runs AC-mapped tests against the
# live endpoints, and ALWAYS tears everything down (cost guard). Idempotent +
# rerunnable. Validated 2026-06-11 on acct 533267307120 / eu-west-2.
#
# Usage:  bash conductor.sh            # deploy → verify → teardown
#         bash conductor.sh --keep     # leave it running (teardown skipped — you must destroy later)
#         ENVRC=/path/.envrc REGION=eu-west-2 SPEC=parrdemo bash conductor.sh
set -euo pipefail

SPEC="${SPEC:-parrdemo}"
REGION="${REGION:-eu-west-2}"
ENVRC="${ENVRC:-/home/olafkfreund/Source/Calitti/Synechron_ARC/sarc/.envrc}"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1
W="${W:-/tmp/run-aws-demo}"
INFRA="$W/infra"

c(){ printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }
ok(){ printf '\033[1;32m✓ %s\033[0m\n' "$1"; }
die(){ printf '\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }
# Run one terraform step with its output in a log (no pipe, so the exit status
# is not lost). On failure quote the log tail and, for the known App Runner
# account restriction, say what the owner has to do.
run_tf(){
  local step="$1"; shift
  local log="$W/tf-$step.log"
  if ! terraform -chdir="$INFRA" "$@" >"$log" 2>&1; then
    tail -15 "$log" >&2
    if grep -q "can't create new App Runner services" "$log"; then
      echo "App Runner is closed for new services on account ${ACCT:-?}. Owner step: open an AWS" >&2
      echo "support case to enable App Runner service creation (or use another account)." >&2
      echo "See docs/aws-app-runner-restriction.md." >&2
    fi
    die "FAILED at $step: terraform $1 (log: $log)"
  fi
  tail -1 "$log"
}

# ---- prereqs ----
for t in terraform docker aws curl python3; do command -v "$t" >/dev/null 2>&1 || die "missing tool: $t"; done
docker info >/dev/null 2>&1 || die "docker daemon not running"
[ -f "$ENVRC" ] || die "AWS creds file not found: $ENVRC (set ENVRC=...)"
getval(){ grep -iE "^[[:space:]]*(export[[:space:]]+)?$1=" "$ENVRC" | tail -1 | sed -E "s/^[^=]*=//; s/^[\"']//; s/[\"'][[:space:]]*\$//" || true; }
AWS_ACCESS_KEY_ID="$(getval AWS_ACCESS_KEY_ID)"
AWS_SECRET_ACCESS_KEY="$(getval AWS_SECRET_ACCESS_KEY)"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION="$REGION"
[ -n "${AWS_ACCESS_KEY_ID:-}" ] || die "AWS_ACCESS_KEY_ID not found in $ENVRC"
ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || die "AWS auth failed"
REG="${ACCT}.dkr.ecr.${REGION}.amazonaws.com"

cleanup_failed=0
teardown(){
  local rc=$?
  set +e   # cleanup must run every command and keep the primary status
  if [ "$KEEP" = "1" ]; then echo; ok "--keep set; LEAVING infra running. Destroy later: terraform -chdir=$INFRA destroy -auto-approve"; exit "$rc"; fi
  c "TEARDOWN (cost guard — always runs)"
  if [ -d "$INFRA/.terraform" ]; then
    if terraform -chdir="$INFRA" destroy -auto-approve -input=false -no-color >"$W/tf-destroy.log" 2>&1; then tail -1 "$W/tf-destroy.log"
    else cleanup_failed=1; tail -5 "$W/tf-destroy.log" >&2; echo "✗ terraform destroy FAILED" >&2; fi
  fi
  # App Runner creates /aws/apprunner/<svc>/<id>/{application,service} CloudWatch
  # log groups that destroy/delete-service does NOT remove — sweep them here.
  local lgs lg
  lgs=$(aws logs describe-log-groups --region "$REGION" \
      --log-group-name-prefix "/aws/apprunner/factory-${SPEC}-" \
      --query 'logGroups[].logGroupName' --output text) || { cleanup_failed=1; echo "✗ log group listing FAILED" >&2; lgs=""; }
  for lg in $lgs; do
    aws logs delete-log-group --log-group-name "$lg" --region "$REGION" || { cleanup_failed=1; echo "✗ delete $lg FAILED" >&2; }
  done
  echo "App Runner services tagged spec=$SPEC remaining:"
  aws apprunner list-services --region "$REGION" \
    --query "ServiceSummaryList[?contains(ServiceName,'factory-${SPEC}')].ServiceName" --output json || cleanup_failed=1
  echo "App Runner log groups for factory-${SPEC}- remaining:"
  aws logs describe-log-groups --region "$REGION" \
    --log-group-name-prefix "/aws/apprunner/factory-${SPEC}-" \
    --query 'logGroups[].logGroupName' --output json || cleanup_failed=1
  if [ "$rc" -eq 0 ] && [ "$cleanup_failed" = "1" ]; then
    echo "✗ teardown failed, AWS resources may remain (check the output above)" >&2; exit 1
  fi
  exit "$rc"
}
# Pre-flight (read-only, before the trap is armed and before the old workspace
# is removed, so a failure here can never destroy anything). It proves identity,
# region and App Runner API access; it cannot prove that CreateService is allowed
# (the account restriction only shows up at apply).
aws apprunner list-services --region "$REGION" --max-items 1 >/dev/null 2>&1 \
  || die "pre-flight failed: cannot list App Runner services in $REGION for account $ACCT (permissions or region)"
trap teardown EXIT
trap 'exit 130' INT TERM

c "0 · Identity"; echo "account $ACCT · region $REGION · spec $SPEC"

# ---- scaffold app + tests ----
c "1 · Scaffold 2 FastAPI services + AC tests"
rm -rf "$W"; mkdir -p "$W/frontend" "$W/scoreboard" "$W/tests" "$INFRA"
cat > "$W/frontend/main.py" <<'PY'
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI(title="frontend")
LINES=[(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
class Move(BaseModel):
    board: list[str]; cell: int; player: str
def status(b):
    for a,c,d in LINES:
        if b[a] and b[a]==b[c]==b[d]: return f"win:{b[a]}"
    return "draw" if all(b) else "in-progress"
@app.get("/healthz")
def h(): return {"ok": True}
@app.get("/")
def r(): return {"service":"frontend","game":"tic-tac-toe"}
@app.post("/move")
def move(m: Move):
    b=list(m.board)
    if 0<=m.cell<9 and not b[m.cell]: b[m.cell]=m.player
    return {"board":b,"status":status(b)}
PY
cat > "$W/scoreboard/main.py" <<'PY'
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
app=FastAPI(title="scoreboard"); TOKEN=os.environ.get("SCORE_TOKEN","secret-token"); _s={}
class Result(BaseModel):
    player: str; won: bool
@app.get("/healthz")
def h(): return {"ok": True}
@app.post("/scores", status_code=201)
def post(r: Result, authorization: str = Header(default="")):
    if authorization!=f"Bearer {TOKEN}": raise HTTPException(401,"unauthorized")
    x=_s.setdefault(r.player,{"player":r.player,"wins":0,"games":0}); x["games"]+=1
    if r.won: x["wins"]+=1
    return x
@app.get("/scores")
def get(): return sorted(_s.values(), key=lambda s: s["wins"], reverse=True)
PY
for svc in frontend scoreboard; do
  printf 'fastapi\nuvicorn[standard]\n' > "$W/$svc/requirements.txt"
  cat > "$W/$svc/Dockerfile" <<'D'
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
D
done
cat > "$W/tests/test_live.py" <<'PY'
import os, httpx
FE=os.environ["FRONTEND_URL"].rstrip("/"); SB=os.environ["SCOREBOARD_URL"].rstrip("/")
TOK=os.environ.get("SCORE_TOKEN","secret-token"); H={"Authorization":f"Bearer {TOK}"}
def test_frontend_health(): assert httpx.get(f"{FE}/healthz",timeout=20).status_code==200
def test_move_win():  # AC: win detection
    assert httpx.post(f"{FE}/move",json={"board":["X","X","","","","","","",""],"cell":2,"player":"X"},timeout=20).json()["status"]=="win:X"
def test_auth_required():  # AC: unauthorized rejected
    assert httpx.post(f"{SB}/scores",json={"player":"a","won":True},timeout=20).status_code==401
def test_auth_ok():  # AC: authorized accepted
    assert httpx.post(f"{SB}/scores",json={"player":"a","won":True},headers=H,timeout=20).status_code==201
def test_leaderboard_sorted():  # AC: sorted by wins
    for _ in range(3): httpx.post(f"{SB}/scores",json={"player":"b","won":True},headers=H,timeout=20)
    w=[r["wins"] for r in httpx.get(f"{SB}/scores",timeout=20).json()]; assert w==sorted(w,reverse=True)
PY
ok "scaffolded frontend + scoreboard + 5 AC tests"

# ---- deterministic terraform (App Runner) ----
c "2 · Generate deterministic App Runner Terraform"
{
cat <<TF
terraform {
  required_version = ">= 1.5"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
}
provider "aws" {
  region = "$REGION"
  default_tags { tags = { "factory-ephemeral" = "true", "spec_id" = "$SPEC", "managed-by" = "factory" } }
}
variable "image_tag" {
  type    = string
  default = "latest"
}
resource "aws_iam_role" "ar" {
  name = "factory-$SPEC-ecr"
  assume_role_policy = jsonencode({ Version="2012-10-17", Statement=[{ Action="sts:AssumeRole", Effect="Allow", Principal={ Service="build.apprunner.amazonaws.com" } }] })
}
resource "aws_iam_role_policy_attachment" "ar" {
  role = aws_iam_role.ar.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}
TF
for svc in frontend scoreboard; do
cat <<TF
resource "aws_ecr_repository" "$svc" {
  name                 = "factory-$SPEC-$svc"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}
resource "aws_apprunner_service" "$svc" {
  service_name = "factory-$SPEC-$svc"
  source_configuration {
    authentication_configuration { access_role_arn = aws_iam_role.ar.arn }
    image_repository {
      image_identifier = "\${aws_ecr_repository.$svc.repository_url}:\${var.image_tag}"
      image_repository_type = "ECR"
      image_configuration { port = "8000" }
    }
    auto_deployments_enabled = false
  }
  instance_configuration {
    cpu    = "256"
    memory = "512"
  }
}
output "url_$svc" { value = "https://\${aws_apprunner_service.$svc.service_url}" }
output "ecr_$svc" { value = aws_ecr_repository.$svc.repository_url }
TF
done
} > "$INFRA/main.tf"
run_tf init init -input=false -no-color >/dev/null
run_tf validate validate -no-color >/dev/null
ok "terraform valid (App Runner x2, factory-ephemeral tagged)"

c "3 · Create ECR repos + IAM role"
run_tf apply-ecr apply -auto-approve -input=false -no-color \
  -target=aws_iam_role.ar -target=aws_iam_role_policy_attachment.ar \
  -target=aws_ecr_repository.frontend -target=aws_ecr_repository.scoreboard >/dev/null
ok "ECR + role ready"

c "4 · Build + push images to ECR"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REG" >/dev/null 2>&1 || die "ecr login failed"
for svc in frontend scoreboard; do
  TAG="${REG}/factory-${SPEC}-${svc}:latest"
  docker build --platform linux/amd64 -q -t "$TAG" "$W/$svc" >/dev/null || die "build $svc failed"
  docker push -q "$TAG" >/dev/null 2>&1 || docker push "$TAG" >/dev/null || die "push $svc failed"
  ok "pushed $svc"
done

c "5 · terraform apply — provision App Runner (real, ~3-4 min/service)"
run_tf apply apply -auto-approve -input=false -no-color
FE=$(terraform -chdir="$INFRA" output -raw url_frontend) || die "FAILED: no url_frontend output after apply"
SB=$(terraform -chdir="$INFRA" output -raw url_scoreboard) || die "FAILED: no url_scoreboard output after apply"
case "$FE" in https://?*) ;; *) die "FAILED: empty or invalid frontend URL '$FE'";; esac
case "$SB" in https://?*) ;; *) die "FAILED: empty or invalid scoreboard URL '$SB'";; esac
ok "frontend  → $FE"; ok "scoreboard → $SB"

c "6 · The live API works (real HTTPS on AWS)"
echo "GET $FE/ →"; curl -s -m 25 "$FE/" || true; echo
echo "POST $FE/move (X wins) →"; curl -s -m 25 -X POST "$FE/move" -H 'content-type: application/json' -d '{"board":["X","X","","","","","","",""],"cell":2,"player":"X"}' || true; echo
echo "POST $SB/scores no-token →"; curl -s -m 25 -o /dev/null -w 'HTTP %{http_code}\n' -X POST "$SB/scores" -H 'content-type: application/json' -d '{"player":"a","won":true}' || true

c "7 · AC verification against the LIVE endpoints (TFactory-style)"
export FRONTEND_URL="$FE" SCOREBOARD_URL="$SB" SCORE_TOKEN="secret-token" TFACTORY_TARGET_URL="$FE"
if python3 -m pytest "$W/tests" -v >"$W/pytest.log" 2>&1; then tail -12 "$W/pytest.log"
else tail -25 "$W/pytest.log" >&2; die "FAILED at step 7: AC tests failed against the live endpoints"; fi

c "8 · DONE"; ok "deploy → live API → AC verification all GREEN on real AWS"
