"""Remove already-indexed scheduled or active live broadcasts from Elasticsearch."""

import argparse
import base64
import os
import sys

import requests


def unfinished_live_query(video_ids=None):
    filters = [{"term": {"isLive": True}}]
    if video_ids is not None:
        filters.append({"terms": {"_id": video_ids}})
    return {
        "bool": {
            "filter": filters,
            "must_not": [{"exists": {"field": "actualEndTime"}}],
        }
    }


def request_options():
    headers = {"Content-Type": "application/json"}
    username = os.getenv("ELASTICSEARCH_ADMIN")
    password = os.getenv("ELASTICSEARCH_PASSWORD")
    if username and password:
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
    return {
        "headers": headers,
        "verify": os.getenv("ELASTICSEARCH_CA") or True,
        "timeout": 60,
    }


def find_candidates(es_url, index_name):
    response = requests.post(
        f"{es_url}/{index_name}/_search",
        json={
            "size": 10000,
            "sort": ["_id"],
            "track_total_hits": True,
            "_source": ["title", "video_url", "isLive", "actualEndTime"],
            "query": unfinished_live_query(),
        },
        **request_options(),
    )
    response.raise_for_status()
    hits = response.json()["hits"]
    total = hits["total"]["value"] if isinstance(hits["total"], dict) else hits["total"]
    if total != len(hits["hits"]):
        raise RuntimeError(f"Candidate result was truncated ({len(hits['hits'])}/{total}); refusing cleanup")
    return hits["hits"]


def delete_candidates(es_url, index_name, video_ids):
    response = requests.post(
        f"{es_url}/{index_name}/_delete_by_query",
        params={"refresh": "true", "conflicts": "abort"},
        json={"query": unfinished_live_query(video_ids)},
        **request_options(),
    )
    response.raise_for_status()
    result = response.json()
    if result.get("failures"):
        raise RuntimeError(f"Elasticsearch reported deletion failures: {result['failures']}")
    return result.get("deleted", 0)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List or remove videos where isLive=true and actualEndTime is absent."
    )
    parser.add_argument("--execute", action="store_true", help="Delete the listed candidates")
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Required with --execute; abort unless the candidate count matches",
    )
    args = parser.parse_args(argv)
    if args.execute and args.expected_count is None:
        parser.error("--expected-count is required with --execute")
    return args


def main(argv=None):
    args = parse_args(argv)
    es_url = os.environ["ELASTICSEARCH_URL"].rstrip("/")
    index_name = os.environ["VIDEOS_INDEX_NAME"]
    candidates = find_candidates(es_url, index_name)

    print(f"Candidates: {len(candidates)}")
    for hit in candidates:
        print(f"{hit['_id']}\t{hit.get('_source', {}).get('title', '')}")

    if not args.execute:
        print("Dry run only. Re-run with --execute --expected-count <count> to delete these documents.")
        return 0
    if len(candidates) != args.expected_count:
        print(
            f"Candidate count changed: expected {args.expected_count}, found {len(candidates)}; aborting.",
            file=sys.stderr,
        )
        return 1
    if not candidates:
        print("No documents to delete.")
        return 0

    deleted = delete_candidates(es_url, index_name, [hit["_id"] for hit in candidates])
    if deleted != len(candidates):
        raise RuntimeError(f"Deleted {deleted} of {len(candidates)} candidate documents")
    print(f"Deleted: {deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
