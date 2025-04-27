import subprocess
import sys
import re
'''
This script reads a markdown file containing issues formatted with level 2 headers (##) and creates GitHub issues for each section.
The script uses the GitHub CLI (gh) to create issues in a specified repository and project.
The markdown file should be formatted as follows:
## Issue Title 1
Issue body for issue 1.
## Issue Title 2
Issue body for issue 2.

# This script is intended to be run from the command line.
# It requires the GitHub CLI (gh) to be installed and authenticated.
# It also requires Python 3.x and the subprocess module.


Example usage:
python create_issues_from_markdown.py sprint1.md yourusername/yourrepo "Your Project Name"
Make sure to have the GitHub CLI installed and authenticated.
The script takes three arguments:
1. Path to the markdown file (e.g., sprint1.md)
2. GitHub repository in the format yourusername/yourrepo
3. Project name in quotes (e.g., "Your Project Name")


'''

# --- FUNCTIONS ---

def parse_markdown(filepath):
    issues = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split on level 2 headers
    sections = re.split(r'\n##\s+', content)
    for section in sections:
        if not section.strip():
            continue  # skip empty

        lines = section.strip().split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[1:]).strip()

        # Safety: if title is empty, skip
        if not title:
            continue

        issues.append((title, body))

    return issues


def create_issue(title, body, repo, project):
    print(f"Creating issue: {title}")
    command = [
        "gh", "issue", "create",
        "--title", title,
        "--body", body,
        "--repo", repo,
        "--project", project
    ]
    subprocess.run(command, check=True)


def main(markdown_file, repo, project):
    issues = parse_markdown(markdown_file)
    print(f"Found {len(issues)} issues to create.")

    for title, body in issues:
        create_issue(title, body, repo, project)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python create_issues_from_markdown.py sprint1.md yourusername/yourrepo \"Your Project Name\"")
        sys.exit(1)

    markdown_file = sys.argv[1]
    repo = sys.argv[2]
    project = sys.argv[3]

    main(markdown_file, repo, project)
