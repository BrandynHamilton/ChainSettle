import requests

#Github attestation helper functions
def github_tag_exists(owner: str, repo: str, tag: str) -> bool:
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    headers = {"Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        tags = [t["name"] for t in response.json()]
        return tag in tags
    return False

def github_file_exists(owner: str, repo: str, path: str, branch="main", return_size=True):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    response = requests.get(url)
    if response.status_code == 200:
        if return_size:
            file_info = response.json()
            return True, file_info.get("size", -1)
        return True
    return (False, -1) if return_size else False