import argparse
from twitter_pipeline import run_all_twitter_sites, MAX_BLOGS_PER_CYCLE

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitter → Auto-Blog Autopilot Orchestrator")
    parser.add_argument("--test", action="store_true", help="Dry run — no publishing")
    parser.add_argument("--handles", nargs="+", help="Twitter handles to scrape (e.g., @sama karpathy)")
    parser.add_argument("--max-blogs", type=int, default=MAX_BLOGS_PER_CYCLE, help="Max blogs to publish per run")
    args = parser.parse_args()

    # Clean handles
    handles = None
    if args.handles:
        handles = [h.lstrip('@').strip() for h in args.handles]
        print(f"[CLI] Using custom handles: {handles}")

    if args.test:
        print("⚠️  DRY RUN MODE — No posts will actually be published")

    run_all_twitter_sites(
        dry_run=args.test,
        handles_override=handles,
        max_blogs_per_site=args.max_blogs,
    )
