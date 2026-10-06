#!/usr/bin/env python3
"""
High-performance batch migration script to generate RRO 2.0 APKs and
flashable Magisk module ZIPs for all existing pointers.
"""

import os
import sys
import json
import argparse
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

from compile_rro import build_rro, package_magisk_module, find_android_tools


def load_pointer_names(cache_file="data/pointer_names.json"):
    cache_path = Path(cache_file)
    if cache_path.is_file():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                names = json.load(f)
                if names:
                    print(f"[*] Loaded {len(names)} pointer names from cache: {cache_file}")
                    return names
        except Exception as e:
            print(f"[!] Warning reading cache {cache_file}: {e}")

    names_map = {}
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        key_json = os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS", "release/pointer-replacer-sa.json"
        )
        if not os.path.isabs(key_json) and not os.path.isfile(key_json):
            alt = Path(__file__).resolve().parent.parent / key_json
            if alt.is_file():
                key_json = str(alt)

        if os.path.isfile(key_json):
            cred = credentials.Certificate(key_json)
            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("[*] Fetching pointer names from Firestore...")
            docs = db.collection("pointers").stream()
            for doc in docs:
                data = doc.to_dict()
                fname = data.get("filename")
                name = data.get("name")
                if fname and name:
                    stem = Path(fname).stem
                    names_map[stem] = name
                    names_map[fname] = name
            print(f"[✓] Fetched {len(names_map)} pointer names from Firestore.")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(names_map, f, indent=2)
        else:
            print("[!] Firestore credentials not found. Using filename fallback if cache not present.")
    except Exception as e:
        print(f"[!] Warning fetching pointer names: {e}")

    return names_map


def process_pointer(args_tuple):
    img_path_str, rros_dir_str, modules_dir_str, pointer_name, force = args_tuple
    img_path = Path(img_path_str)
    rros_dir = Path(rros_dir_str)
    modules_dir = Path(modules_dir_str)

    stem = img_path.stem
    apk_out = rros_dir / f"RRO_{stem}.apk"
    zip_out = modules_dir / f"RRO_{stem}.zip"

    apk_exists = apk_out.is_file()
    zip_exists = zip_out.is_file()

    if apk_exists and zip_exists and not force:
        return stem, "SKIPPED", None

    try:
        # Build RRO 2.0 APK
        build_rro(
            image_path=str(img_path),
            package_name="com.afterroot.allusive_rro",
            target_package="android",
            output_apk=str(apk_out),
            priority=99,
        )

        display_name = (
            f"Pointer Replacer RRO - {pointer_name}" if pointer_name else f"Pointer Replacer RRO - {stem}"
        )

        # Package flashable Magisk Module ZIP with Firestore pointer name
        package_magisk_module(
            apk_path=str(apk_out),
            output_zip=str(zip_out),
            module_id="pointer_replacer_rro",
            module_name=display_name,
            pointer_name=pointer_name,
            author="thesandipv",
            version="v2.0",
            version_code=2,
        )

        return stem, "SUCCESS", None
    except Exception as exc:
        return stem, "FAILED", str(exc)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate all pointers to RRO 2.0 APKs & Flashable Magisk Module ZIPs"
    )
    parser.add_argument(
        "--pointers-dir",
        type=str,
        default="repo/pointers",
        help="Directory containing source pointer images",
    )
    parser.add_argument(
        "--rros-dir",
        type=str,
        default="repo/rros",
        help="Directory to save compiled RRO 2.0 APKs",
    )
    parser.add_argument(
        "--modules-dir",
        type=str,
        default="repo/modules",
        help="Directory to save flashable Magisk Module ZIPs",
    )
    parser.add_argument(
        "--cache-file",
        type=str,
        default="data/pointer_names.json",
        help="Path to JSON cache of Firestore pointer names",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 4,
        help="Number of parallel worker processes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of pointers to process (useful for testing)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-generation even if output files already exist",
    )
    args = parser.parse_args()

    # Pre-flight check for build tools
    try:
        find_android_tools()
    except SystemExit:
        print("[!] Error: Android SDK build tools not found. Aborting.")
        sys.exit(1)

    pointers_dir = Path(args.pointers_dir).resolve()
    rros_dir = Path(args.rros_dir).resolve()
    modules_dir = Path(args.modules_dir).resolve()

    if not pointers_dir.is_dir():
        print(f"[!] Error: {pointers_dir} is not a valid directory")
        sys.exit(1)

    rros_dir.mkdir(parents=True, exist_ok=True)
    modules_dir.mkdir(parents=True, exist_ok=True)

    pointer_names = load_pointer_names(cache_file=args.cache_file)

    images = sorted(list(pointers_dir.glob("*.png")))
    if args.limit:
        images = images[: args.limit]

    total = len(images)
    print(f"[*] Found {total} pointer images in {pointers_dir}")
    print(f"[*] Compiling RRO 2.0 APKs to: {rros_dir}")
    print(f"[*] Packaging Magisk Module ZIPs to: {modules_dir}")
    print(f"[*] Worker processes: {args.workers} | Force rebuild: {args.force}")

    tasks = [
        (
            str(img),
            str(rros_dir),
            str(modules_dir),
            pointer_names.get(img.stem) or pointer_names.get(img.name),
            args.force,
        )
        for img in images
    ]

    start_time = time.time()
    success_count = 0
    skipped_count = 0
    failed_count = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_pointer, t): t[0] for t in tasks}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            stem, status, err = future.result()
            if status == "SUCCESS":
                success_count += 1
                if completed % 50 == 0 or completed == total:
                    print(f"[{completed}/{total}] ✓ Processed {stem}")
            elif status == "SKIPPED":
                skipped_count += 1
            else:
                failed_count += 1
                print(f"[{completed}/{total}] ✗ Failed {stem}: {err}")

    elapsed = time.time() - start_time
    print("\n========================================")
    print(f"[*] Migration finished in {elapsed:.2f}s")
    print(f"    - Total:   {total}")
    print(f"    - Success: {success_count}")
    print(f"    - Skipped: {skipped_count}")
    print(f"    - Failed:  {failed_count}")
    print("========================================")


if __name__ == "__main__":
    main()
