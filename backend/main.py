from flask import Flask, request, jsonify
import os
import datetime as dt
from datetime import timedelta
from dotenv import load_dotenv

from chainsettle import (wire_api, plaid_api, github_tag_exists, github_file_exists)

load_dotenv()

PORT = os.getenv('PORT', 5045)
GIT_COMMIT = os.getenv('GIT_COMMIT_HASH', 'unknown')
BUILD_TIME = os.getenv('BUILD_TIME', 'unknown')

# Flask App Factory
def create_app():
    app = Flask(__name__)

    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "ok",
            "git_commit": GIT_COMMIT,
            "build_time": BUILD_TIME,
        })

    @app.route('/api/initiate_attestation', methods=['POST'])
    def init_req():
        data = request.get_json()

        attestation_type = data.get('type')  # 'swift/wire', 'github', etc.

        if attestation_type == 'wire':
            wire_id = data.get('wire_id', 'mt103-default')
            amount = data.get('amount', 100000)
            result = wire_api(wire_id, amount)
            return jsonify(result)

        elif attestation_type == 'plaid':
            tx_id = data.get('tx_id', "txn-9911")
            amount = data.get('amount', 100000)
            result = plaid_api(tx_id, amount)
            return jsonify(result)

        elif attestation_type == 'github':
            owner = data.get('owner')
            repo = data.get('repo')
            tag = data.get('tag')
            path = data.get('path')
            branch = data.get('branch', 'main')

            # Run checks
            tag_ok = github_tag_exists(owner, repo, tag)
            file_ok = github_file_exists(owner, repo, path, branch)

            # Build base response
            base_response = {
                "repo": f"{owner}/{repo}",
                "tag": tag,
                "path": path,
                "branch": branch,
                "tag_confirmed": tag_ok,
                "file_confirmed": file_ok,
                "timestamp": dt.datetime.utcnow().isoformat()
            }

            if tag_ok and file_ok:
                base_response["status"] = "confirmed"
            elif tag_ok:
                base_response["status"] = "partial"
                base_response["message"] = f"Tag exists but file `{path}` not found in `{branch}`"
            elif file_ok:
                base_response["status"] = "partial"
                base_response["message"] = f"File exists but tag `{tag}` not found"
            else:
                base_response["status"] = "unconfirmed"
                base_response["message"] = "Neither tag nor file could be verified"

            return jsonify(base_response)

    return app

if __name__ == "__main__":
    print("Git Commit Hash:", GIT_COMMIT)
    print("Build Timestamp:", BUILD_TIME)
    print('Starting ChainSettle Mock API...')
    app = create_app()
    app.run(host='0.0.0.0', debug=True, use_reloader=False, port=int(PORT))
