#!/usr/bin/env python3
import argparse
import subprocess
import os
import json

BLACKLIST_MODULES = [
    "hbase-assembly",
    "hbase-archetypes",
]

def is_blacklisted(module_path):
    for bad in BLACKLIST_MODULES:
        if module_path == bad or module_path.startswith(bad + "/"):
            return True
    return False

def find_module_for_file(repo, filepath):
    current_dir = os.path.dirname(filepath) if filepath else ""
    while current_dir:
        pom_path = os.path.join(repo, current_dir, "pom.xml")
        if os.path.exists(pom_path):
            if not is_blacklisted(current_dir):
                return current_dir
            else:
                return None
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
    return None

def extract_test_class(filepath):
    if "/src/test/java/" not in filepath:
        return None
    try:
        class_part = filepath.split("/src/test/java/")[1]
        return class_part.replace("/", ".").replace(".java", "")
    except Exception:
        return None

def is_test_file(filepath):
    filename = os.path.basename(filepath)
    return (
        "/src/test/java/" in filepath and
        filepath.endswith(".java") and
        (filename.startswith("Test") or filename.endswith("Test.java") or
         filename.endswith("Tests.java") or filename.endswith("IT.java"))
    )

def is_source_file(filepath):
    return "/src/main/java/" in filepath and filepath.endswith(".java")

def _entries_from_worktree(repo):
    entries = []
    for extra in ([], ["--cached"]):
        try:
            out = subprocess.check_output(
                ["git", "diff", *extra, "--name-status"],
                cwd=repo, text=True,
            )
            for line in out.strip().splitlines():
                parts = line.split("\t")
                if not parts:
                    continue
                status = parts[0]
                if status.startswith("R") or status.startswith("C"):
                    fp = parts[2] if len(parts) >= 3 else None
                else:
                    fp = parts[1] if len(parts) >= 2 else None
                if fp:
                    entries.append((status[0], fp))
        except subprocess.CalledProcessError:
            pass
    return entries

def process_entries(entries, repo):
    modified_tests = set()
    added_tests = set()
    source_modules = set()
    all_modules = set()

    for status, filepath in entries:
        filepath = filepath.replace("\\", "/")
        module = find_module_for_file(repo, filepath)
        if module:
            all_modules.add(module)

        if is_test_file(filepath):
            if not module:
                continue
            class_name = extract_test_class(filepath)
            test_target = f"{module}:{class_name}" if class_name else module
            if status == "A":
                added_tests.add(test_target)
            else:
                modified_tests.add(test_target)
        elif is_source_file(filepath) and module:
            source_modules.add(module)

    return modified_tests, added_tests, source_modules, all_modules

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--files-json", default=None)
    parser.add_argument("--worktree", action="store_true")
    args = parser.parse_args()

    entries = []

    if args.files_json is not None:
        try:
            raw = json.loads(args.files_json)
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    entries.append((str(item[0]), str(item[1])))
                else:
                    entries.append(("M", str(item)))
        except Exception:
            entries = []

    elif args.commit:
        cmd = ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", args.commit]
        try:
            output = subprocess.check_output(cmd, cwd=args.repo, text=True)
            for line in output.strip().splitlines():
                parts = line.split("\t")
                if not parts:
                    continue
                status = parts[0]
                if status.startswith("R") or status.startswith("C"):
                    fp = parts[2] if len(parts) >= 3 else None
                else:
                    fp = parts[1] if len(parts) >= 2 else None
                if fp:
                    entries.append((status[0], fp))
        except subprocess.CalledProcessError:
            pass

    elif args.worktree:
        entries = _entries_from_worktree(args.repo)

    modified_tests, added_tests, source_modules, all_modules = process_entries(entries, args.repo)

    print(json.dumps({
        "modified": sorted(modified_tests),
        "added": sorted(added_tests),
        "source_modules": sorted(source_modules),
        "all_modules": sorted(all_modules),
    }))

if __name__ == "__main__":
    main()
