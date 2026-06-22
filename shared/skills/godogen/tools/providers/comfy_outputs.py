from __future__ import annotations


def first_output_file(job: dict, expected_extensions: list[str]) -> dict:
    for node_outputs in job.get("outputs", {}).values():
        for key in ("images", "videos", "audio", "models"):
            for item in node_outputs.get(key, []):
                filename = item.get("filename", "")
                if any(filename.endswith(ext) for ext in expected_extensions):
                    return item
    raise ValueError(f"No Comfy output matched extensions: {expected_extensions}")
