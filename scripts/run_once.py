"""수동 1회 실행 (테스트용).

    python scripts/run_once.py --account demo            # 글 1개 생성 → 초안 저장
    python scripts/run_once.py --account demo --dry-run  # AI 호출 없이 프롬프트만 출력
    python scripts/run_once.py --account demo --publish  # 생성 후 즉시 게시 (토큰 필요)
    python scripts/run_once.py --account demo --ideas    # 글감 수집만
"""
import argparse
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store, service, generator, trend  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="demo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--ideas", action="store_true")
    a = ap.parse_args()
    store.init()

    if a.ideas:
        print("글감 수집:", trend.collect(a.account), "개 저장")
        return

    if a.dry_run:
        topic = generator.pick_topic(a.account)
        print("=== SYSTEM ===\n" + generator.build_system(a.account))
        print("=== USER ===\n" + generator.build_user(topic))
        print("=== 링크 허용:", service.link_allowed(a.account))
        return

    post = service.create_post(a.account, publish=a.publish)
    print(f"\n#{post['id']} [{store.STATUS_LABEL[post['status']]}] 주제: {post['topic']}\n")
    print(post["body"])
    if post["link"]:
        print("\n" + post["link"])
    if post.get("error"):
        print("\n오류:", post["error"])


if __name__ == "__main__":
    main()
