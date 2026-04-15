"""
Diagnostic script — list all mail folders in the signed-in mailbox.
Run: .\venv\Scripts\python.exe diagnose_folders.py

This helps identify:
  1. Which account is currently signed in
  2. The EXACT folder names available (copy-paste into config.json)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import load_config
from src.auth.graph_auth import GraphAuth
from src.graph.client import GraphClient

cfg = load_config()
auth = GraphAuth(
    client_id=cfg.azure.client_id,
    authority=cfg.azure.authority,
    scopes=cfg.azure.scopes,
)

print("=" * 60)
print("DIAGNOSTIC: Mail Folders")
print("=" * 60)

# Show which account is signed in
username = auth.get_username()
if username:
    print(f"Đang đăng nhập với: {username}")
else:
    print("Chưa đăng nhập! Hãy chạy run.bat và đăng nhập trước.")
    sys.exit(1)

token = auth.get_token()
if not token:
    print("Không lấy được token.")
    sys.exit(1)

client = GraphClient(token)

# List all top-level folders
print("\nTất cả thư mục cấp 1:")
print("-" * 60)
top = list(client.paginate(
    "/me/mailFolders",
    params={"$select": "id,displayName,childFolderCount,totalItemCount", "$top": 100}
))

for f in top:
    name = f["displayName"]
    count = f.get("totalItemCount", 0)
    children = f.get("childFolderCount", 0)
    marker = " ← CÓ THƯ MỤC CON" if children > 0 else ""
    print(f"  📁 '{name}'  ({count} email){marker}")

    # Show child folders
    if children > 0:
        try:
            kids = list(client.paginate(
                f"/me/mailFolders/{f['id']}/childFolders",
                params={"$select": "id,displayName,childFolderCount,totalItemCount", "$top": 100}
            ))
            for k in kids:
                kname = k["displayName"]
                kcount = k.get("totalItemCount", 0)
                kchildren = k.get("childFolderCount", 0)
                kmarker = " ← CÓ THƯ MỤC CON" if kchildren > 0 else ""
                print(f"      📂 '{kname}'  ({kcount} email){kmarker}")

                # Level 3
                if kchildren > 0:
                    try:
                        grandkids = list(client.paginate(
                            f"/me/mailFolders/{k['id']}/childFolders",
                            params={"$select": "id,displayName,totalItemCount", "$top": 100}
                        ))
                        for g in grandkids:
                            print(f"          📄 '{g['displayName']}'  ({g.get('totalItemCount', 0)} email)")
                    except Exception:
                        pass
        except Exception as e:
            print(f"      (Không đọc được thư mục con: {e})")

print("\n" + "=" * 60)
print("Tìm kiếm thư mục chứa 'văn' (không phân biệt hoa/thường):")
print("-" * 60)

import unicodedata

def norm(t):
    return unicodedata.normalize("NFC", t).lower().strip()

for f in top:
    if "văn" in norm(f["displayName"]) or "van" in norm(f["displayName"]):
        print(f"  ✅ '{f['displayName']}'")
    try:
        kids = list(client.paginate(
            f"/me/mailFolders/{f['id']}/childFolders",
            params={"$select": "id,displayName", "$top": 100}
        )) if f.get("childFolderCount", 0) > 0 else []
        for k in kids:
            if "văn" in norm(k["displayName"]) or "van" in norm(k["displayName"]):
                print(f"  ✅ (subfolder of '{f['displayName']}') '{k['displayName']}'")
    except Exception:
        pass

print("\n→ Copy tên thư mục chính xác vào config.json → mail.target_folder_name")
print("=" * 60)

