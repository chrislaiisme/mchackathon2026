# 讓評審用自己的電腦連上你的 demo（Cloudflare Quick Tunnel）

目標：評審不用坐到你的電腦前，用自己的筆電/手機打開一個網址就能操作這套系統，實際流量還是打到你這台跑 demo 的機器。

**範圍（這次刻意只做這兩個）：前端（3000）＋ ENGINE01（8000）。** 語音輸入、虛擬試穿這兩個服務**這次不 tunnel**——它們只在使用者主動按麥克風／Try On 時才會被呼叫，demo 現場如果評審沒特別要求測這兩個功能，維持 localhost 也不影響核心流程（登入→對話→推薦→回饋→下一輪）；之後如果要擴大範圍，重複下面同樣的「開 tunnel → 補環境變數 → 重啟」流程即可。

## 為什麼不能只開前端的 tunnel

前端是 Next.js，`NEXT_PUBLIC_API_BASE_URL` 這種 `NEXT_PUBLIC_` 開頭的變數，會在啟動 dev server 時就被讀進去、烤進瀏覽器端會執行的 JS 裡（不是執行期才讀）。也就是說：評審的瀏覽器實際上是直接呼叫這個網址，不是透過你的前端伺服器轉發。如果這個網址還是 `http://127.0.0.1:8000`，評審的瀏覽器連的是**評審自己的電腦**的 8000 port，不是你的——這樣推薦、對話全部連不到。所以 ENGINE01 也必須被 tunnel 出去，前端才有辦法把後端網址換成一個評審連得到的網址。

## 安裝 cloudflared

不需要 Cloudflare 帳號、不需要自己買網域——Quick Tunnel（`cloudflared tunnel --url ...`）是官方免費提供的臨時公開網址功能，跑起來會給一個隨機的 `*.trycloudflare.com` 網址。

```bash
# Windows（PowerShell 或 cmd 都可以）
winget install --id Cloudflare.cloudflared

# macOS
brew install cloudflared

# Linux（Debian/Ubuntu，其他發行版看官方文件抓對應的二進位檔）
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
```

裝完用 `cloudflared --version` 確認能跑。

**代價（一定要先知道，不是細節）：Quick Tunnel 每次啟動都會拿到一個全新的隨機網址，不是固定的。** 這對下面「Google OAuth」那一步是個真正的麻煩，不是隨口提醒，往下看。

## 操作順序（照順序做，不要跳步）

1. **本機先把服務跑起來**（用 [`scripts/dev_services.py`](../scripts/dev_services.py) 或 `scripts/start-demo.ps1` 都可以，這一步都還是 localhost，不用管 tunnel）：

   ```bash
   python scripts/dev_services.py start engine02 engine01 frontend
   ```

2. **對 ENGINE01（8000）開一條 Quick Tunnel**，另開一個終端機視窗，讓它一直開著：

   ```bash
   cloudflared tunnel --url http://127.0.0.1:8000
   ```

   終端機輸出裡會有一行類似 `https://random-two-words-abcd.trycloudflare.com`——**記下這個網址**，下面叫它 `ENGINE01_TUNNEL_URL`。

3. **對前端（3000）開另一條 Quick Tunnel**，再開一個終端機視窗：

   ```bash
   cloudflared tunnel --url http://127.0.0.1:3000
   ```

   一樣記下拿到的網址，下面叫它 `FRONTEND_TUNNEL_URL`。

4. **讓 ENGINE01 接受來自 `FRONTEND_TUNNEL_URL` 的跨來源請求**（CORS）——用剛剛的跨平台腳本重啟 ENGINE01，順便覆蓋 `CORS_ALLOWED_ORIGINS`：

   ```bash
   python scripts/dev_services.py restart engine01 --env CORS_ALLOWED_ORIGINS=FRONTEND_TUNNEL_URL,http://localhost:3000
   ```

   （把 `FRONTEND_TUNNEL_URL` 換成第 3 步拿到的實際網址；後面留著 `http://localhost:3000` 是為了你自己本機還能繼續測試，不會互相排斥。）

5. **讓前端改打 ENGINE01 的 tunnel 網址**：編輯 `frontend/.env.local`，把

   ```
   NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
   ```

   改成

   ```
   NEXT_PUBLIC_API_BASE_URL=ENGINE01_TUNNEL_URL
   ```

   存檔後**一定要重啟前端**（改 `.env.local` 不會熱重載生效，這個變數是啟動時才讀的）：

   ```bash
   python scripts/dev_services.py restart frontend
   ```

6. **Google OAuth 登入——這是最容易漏掉、也最容易卡在 demo 現場的一步。** ENGINE01「必須登入」，登入用的是 Google Identity Services，瀏覽器端會檢查目前的網址是不是在 OAuth Client 的「Authorized JavaScript origins」允許清單裡（跟 [CLAUDE.md](../CLAUDE.md)「Google OAuth Client ID」那節設定的是同一個地方）。這個清單是**固定的**，不會自動接受一個新的 `trycloudflare.com` 網址：

   1. 打開 [console.cloud.google.com](https://console.cloud.google.com/) → APIs & Services → Credentials → 你的 OAuth client ID。
   2. 「Authorized JavaScript origins」加上 `FRONTEND_TUNNEL_URL`（第 3 步拿到的那個網址，要包含 `https://`，不要帶結尾的 `/`）。
   3. 存檔。**Google 這邊生效不一定是即時的**，實測可能要幾分鐘，也可能更久——一定要提早測，不要等評審上場當下才第一次嘗試登入。
   4. **只要重啟第 3 步那條 tunnel，就會拿到一個新網址，Google 這邊也要重新加一次。** 所以：這一步做完、確認登入能動之後，**除非必要不要重啟前端那條 tunnel**（ENGINE01 那條 tunnel 網址不影響 Google OAuth，可以視情況重啟不受影響）。

7. **demo 前提早驗證整條鏈路**：用另一台裝置（手機用行動網路，不要用同一個 Wi-Fi，這樣才是真的在測「別人的電腦連得到」）打開 `FRONTEND_TUNNEL_URL`，走一次完整流程：登入 → 打一句話 → 看到推薦 → 給回饋 → 看到下一輪。全部過一次沒問題才算真的準備好，不要只測到「網頁打得開」就停。

## 如果 Google OAuth 生效來不及

`DEV_BYPASS_AUTH=true` 是這個專案本來就有的開發旁路（見 [CLAUDE.md](../CLAUDE.md)「Google OAuth Client ID」），設定這個環境變數可以跳過登入直接測 `/intent`／`/profile` 等端點。**這是最後手段，不是預設做法**——正式 demo 用跳過登入合不合適，取決於你們想不想在評審面前展示登入流程本身，這裡只記錄這個選項存在，不建議預設採用。真的要用，一樣透過 `python scripts/dev_services.py restart engine01 --env DEV_BYPASS_AUTH=true` 套用。

## 收工後

Quick Tunnel 的網址只在 `cloudflared tunnel` 那個行程還活著的時候有效——直接關掉那兩個終端機視窗（或 Ctrl+C）就完全停止對外開放，不需要另外登出或刪除什麼設定。本機服務要不要一起關，用 `python scripts/dev_services.py stop` 處理。
