"""収集データを S3 にバックアップする（S3 側のファイルは削除しない）。"""

import os
from pathlib import Path

import boto3


BUCKET = "utsulog-s3-bucket"


def main():
    # ホストの utsulog-data は Docker Compose で /app 配下にマウントされる。
    directories = {
        "chat_logs": Path(os.getenv("LOCAL_CHAT_LOGS_DIR", "/app/chat_logs")),
        "comments": Path(os.getenv("LOCAL_COMMENTS_DIR", "/app/comments")),
        "videos": Path(os.getenv("VIDEOS_NDJSON", "/app/videos/videos.ndjson")).parent,
    }
    # マウント漏れを成功扱いにしないよう、アップロード前に全ディレクトリを確認する。
    for directory in directories.values():
        if not directory.is_dir():
            raise FileNotFoundError(f"Backup directory does not exist: {directory}")

    s3 = boto3.client("s3")
    for name, directory in directories.items():
        count = 0
        # os.walk の読み取りエラーもバッチの失敗として扱う。
        def raise_walk_error(error):
            raise error

        for root, dirs, files in os.walk(directory, onerror=raise_walk_error):
            dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
            for filename in files:
                path = Path(root) / filename
                if path.is_symlink() or not path.is_file():
                    continue
                key = f"{name}/{path.relative_to(directory).as_posix()}"
                s3.upload_file(str(path), BUCKET, key)
                count += 1
        print(f"Backed up {count} files from {directory} to s3://{BUCKET}/{name}/", flush=True)


if __name__ == "__main__":
    main()
