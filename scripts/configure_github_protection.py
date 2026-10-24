#!/usr/bin/env python3
"""
configure_github_protection.py

Automates repository security and open-source standards configuration for
https://github.com/karthikrameshdev/Dock-T-w-oo via the GitHub REST API.

Features configured:
1. Repository General Settings:
   - Squash merge only (clean, atomic commit history)
   - Auto-delete head branches upon merge
   - Enable Issues and Discussions
2. Branch Protection Rules on 'main':
   - Require Pull Requests before merging
   - Require review approval from CODEOWNERS (@karthikrameshdev)
   - Dismiss stale pull request approvals when new commits are pushed
   - Require conversation resolution before merging
   - Enforce rules on administrators (prevents accidental direct push)
   - Strictly block force pushes
   - Strictly block branch deletions
3. Repository Rulesets:
   - Restrict branch creation on upstream (contributors must use personal forks)
   - Restrict branch deletion and non-fast-forward pushes
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO_OWNER = "karthikrameshdev"
REPO_NAME = "Dock-T-w-oo"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


def resolve_token():
    # 1. Environment variable
    token = os.environ.get("GITHUB_TOKEN")
    if token and not token.startswith("ghp_placeholder"):
        # Verify user
        if check_token_admin(token):
            return token

    # 2. Check root .env file
    env_file = os.path.expanduser("~/Projects/Self/.env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("GITHUB_TOKEN="):
                    val = line.strip().split("=", 1)[1]
                    if check_token_admin(val):
                        return val

    # 3. Check macOS keychain for karthikrameshdev
    try:
        proc = subprocess.run(
            ["git", "credential-osxkeychain", "get"],
            input=f"protocol=https\nhost=github.com\nusername={REPO_OWNER}\n\n".encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        for line in proc.stdout.decode().splitlines():
            if line.startswith("password="):
                val = line.split("=", 1)[1].strip()
                if check_token_admin(val):
                    return val
    except Exception:
        pass

    return None


def make_request(url, method="GET", data=None, token=None):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Dock-Twoo-Protection-Configurator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, headers=headers, data=body, method=method)
    return urllib.request.urlopen(req)


def check_token_admin(token):
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
        with make_request(url, token=token) as resp:
            data = json.loads(resp.read().decode())
            perms = data.get("permissions", {})
            return perms.get("admin", False)
    except Exception:
        return False


def get_repo_status(token):
    url = f"{API_BASE}"
    with make_request(url, token=token) as resp:
        return json.loads(resp.read().decode())


def make_repo_public(token):
    print("🌐 Setting repository visibility to PUBLIC...")
    url = f"{API_BASE}"
    payload = {"private": False}
    with make_request(url, method="PATCH", data=payload, token=token) as resp:
        data = json.loads(resp.read().decode())
        print(f"✅ Repository visibility updated: Private = {data.get('private')}")


def configure_repo_settings(token):
    print("⚙️  Configuring repository merge and PR settings...")
    url = f"{API_BASE}"
    payload = {
        "has_issues": True,
        "has_projects": True,
        "has_wiki": False,
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "delete_branch_on_merge": True,
        "allow_auto_merge": False,
        "squash_merge_commit_title": "PR_TITLE",
        "squash_merge_commit_message": "PR_BODY",
    }
    with make_request(url, method="PATCH", data=payload, token=token) as resp:
        print("✅ Repository PR and merge settings configured successfully.")


def configure_branch_protection(token):
    print("🔒 Configuring Branch Protection for 'main'...")
    url = f"{API_BASE}/branches/main/protection"
    payload = {
        "required_status_checks": None,
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": 1,
            "require_last_push_approval": True,
        },
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": True,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }
    with make_request(url, method="PUT", data=payload, token=token) as resp:
        print("✅ Branch protection enabled on 'main':")
        print("   - Direct commits blocked")
        print("   - Pull Request required before merging")
        print("   - CODEOWNERS review approval required from @karthikrameshdev")
        print("   - Stale reviews dismissed on new pushes")
        print("   - Conversations must be resolved")
        print("   - Force pushes blocked")
        print("   - Branch deletion blocked")
        print("   - Enforced on administrators")


def configure_rulesets(token):
    print("🛡️  Configuring Repository Ruleset (Restrict Branch Creation)...")
    url = f"{API_BASE}/rulesets"

    # Check if a ruleset with this name already exists
    try:
        with make_request(url, token=token) as resp:
            existing = json.loads(resp.read().decode())
            for rule in existing:
                if rule.get("name") == "Restrict Upstream Branch Creation":
                    print("ℹ️  Ruleset 'Restrict Upstream Branch Creation' already exists.")
                    return
    except Exception:
        pass

    payload = {
        "name": "Restrict Upstream Branch Creation",
        "target": "branch",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": ["~ALL"],
                "exclude": ["refs/heads/main"],
            }
        },
        "rules": [
            {"type": "creation"},
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
    }
    try:
        with make_request(url, method="POST", data=payload, token=token) as resp:
            print("✅ Ruleset 'Restrict Upstream Branch Creation' created successfully:")
            print("   - Direct branch creation on upstream is blocked")
            print("   - External contributors are required to contribute via forks")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        print(f"⚠️  Ruleset API notice: {err_msg}")


def main():
    parser = argparse.ArgumentParser(description="Configure GitHub Protection for Dock T(w)oo")
    parser.add_argument("--make-public", action="store_true", help="Set repository visibility to public")
    parser.add_argument("--status-only", action="store_true", help="Only check and display status")
    args = parser.parse_args()

    token = resolve_token()
    if not token:
        print("❌ Error: Could not resolve a valid GitHub Token with admin permissions.")
        print(f"   Please set GITHUB_TOKEN environment variable with repo/admin scope for {REPO_OWNER}.")
        sys.exit(1)

    print(f"🔑 Authenticated as {REPO_OWNER} (admin access verified).")
    repo = get_repo_status(token)
    is_private = repo.get("private", True)
    print(f"📦 Repository: {repo.get('full_name')} (Private: {is_private})")

    if args.status_only:
        return

    if is_private and not args.make_public:
        print("\n⚠️  NOTICE: This repository is currently PRIVATE on a GitHub Free personal account.")
        print("   GitHub Free requires the repository to be PUBLIC before Branch Protection & Rulesets can be enabled.")
        print("   To make the repository public and apply all protection rules, run:")
        print("   python3 scripts/configure_github_protection.py --make-public\n")
        return

    if is_private and args.make_public:
        make_repo_public(token)

    configure_repo_settings(token)
    configure_branch_protection(token)
    configure_rulesets(token)
    print("\n🎉 Repository is fully protected and configured according to open-source standards!")


if __name__ == "__main__":
    main()
