import glob
import subprocess
import os # osモジュールを追加

video_dir = os.environ.get("VIDEOFILES_DIR")
videos = glob.glob(f"{video_dir}/*.mp4")

# --- 変換後のMP3を保存するフォルダを作成 ---
output_dir = os.environ.get("AUDIOS_DIR")
os.makedirs(output_dir, exist_ok=True)
# -------------------------------------

print(f"--- {len(videos)}件のファイルを変換します ---")

for src in videos:
    # 出力ファイル名を生成（フォルダ名部分も変更）
    base_name = os.path.basename(src) # "audios/video1.mp4" -> "video1.mp4"
    file_name = os.path.splitext(base_name)[0] # "video1.mp4" -> "video1"
    dest = os.path.join(output_dir, f"{file_name}.mp3") # "audios_mp3/video1.mp3"

    if os.path.exists(dest):
        print(f"スキップ: {dest} (すでに存在します)")
        continue
    
    print(f"変換中: {src} -> {dest}")

    # ffmpegコマンドの引数リスト
    command = [
        'ffmpeg',
        '-i', src,         # 入力ファイル
        '-vn',             # ビデオなし
        '-c:a', 'libmp3lame', # オーディオコーデック: MP3
        '-b:a', '64k',     # ビットレート: 64kbps
        '-ac', '1',        # チャンネル: 1 (モノラル)
        '-ar', '16000',    # サンプルレート: 16000 Hz (16kHz)
        '-y',              # 警告なしで上書き
        dest               # 出力ファイル
    ]
    
    # コマンドを実行
    cp = subprocess.run(command)
    
    if cp.returncode == 0:
        print(f"成功: {dest}")
    else:
        print(f"失敗: {src}")

print("--- すべての処理が完了しました ---")