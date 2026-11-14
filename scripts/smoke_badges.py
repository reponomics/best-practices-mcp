"""Opt-in paced production reads for both badge tools; no browser or remote writes."""

import argparse
import asyncio
import json

from best_practices_mcp.badges import get_project_badge_status, get_project_badge_svg
from best_practices_mcp.http import BadgeAppHTTP
from best_practices_mcp.sdk_adapter import tool_result


async def probe(project_id: int) -> list[dict]:
    observations = []
    async with BadgeAppHTTP() as http:
        for family in ("best_practices", "baseline"):
            status = await get_project_badge_status(http, project_id, family)
            image = await get_project_badge_svg(http, project_id, family)
            # Validate schemas and the complete serialized result budgets.
            tool_result("get_project_badge_status", status)
            tool_result("get_project_badge_svg", image)
            observations.append(
                {
                    "project_id": project_id,
                    "family": family,
                    "status_source": status["observation"]["source_url"],
                    "status_fetched_at": status["observation"]["fetched_at"],
                    "badge_level": status["badge_level"],
                    "updated_at_status": status["updated_at_status"],
                    "svg_source": image["observation"]["source_url"],
                    "svg_fetched_at": image["observation"]["fetched_at"],
                    "svg_size_bytes": image["artifact"]["encoded_size_bytes"],
                }
            )
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, default=1)
    args = parser.parse_args()
    if args.project_id <= 0:
        parser.error("--project-id must be positive")
    print(json.dumps(asyncio.run(probe(args.project_id)), indent=2))


if __name__ == "__main__":
    main()
