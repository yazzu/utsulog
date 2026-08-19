# 投稿日時フィルターと「前後5分を表示」コマンド Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 検索フィルターの投稿日を投稿日時(時刻まで)に拡張し、検索結果カードから「前後5分のチャットを表示」できるショートカットコマンドを追加する。

**Architecture:** フロントエンド(React/TS)が日付inputと任意の時刻inputを組み合わせ、純粋関数で完全なISO日時文字列に変換してからAPIへ送る。バックエンド(FastAPI)は日時範囲のElasticsearchフィルター構築を純粋関数に切り出し、`gte`/`lte`のみで境界を扱う(既存の「+1日」ハックは廃止)。カードの時計アイコンは現在の検索条件一式をスナップショットし、対象カードと同じ動画内の±5分にフィルターを差し替えて再検索し、スクロールに追従するバナーから元の検索へ復元できるようにする。

**Tech Stack:** React 19 + TypeScript + Vite(フロントエンド)、FastAPI + Elasticsearch Python client(API)。テストには新規に pytest(API)と vitest(フロントエンド)を導入する。

## Global Constraints

- `date_from`/`date_to` はAPIに常に完全なISO日時文字列(例 `"2026-07-10T22:00:00"`)として渡す。日付のみの文字列は送らない。
- 秒の補完は常に固定: `date_from` の秒は常に `:00`、`date_to` の秒は常に `:59`(時刻が未入力の場合のデフォルト値・ユーザーが明示入力した場合のいずれも同じ固定ルール)。
- 「前後5分を表示」は対象カードと同じ動画内(`selectedVideoId`をセット)に限定する。前後の分数は固定5分(可変にしない)。
- 「前後5分を表示」実行時にリセットする項目: `searchQuery` → `''`、`authorName` → `''`、`messageType` → `'all'`、`sortOrder` → `'asc'`。
- バナーの文言は実際に適用中のFrom/To日時を表示する汎用表現にする(「前後5分」のような固定文言は使わない。手動で範囲を微調整しても表示が破綻しないようにするため)。
- バナーは `sticky top-0` で無限スクロールに追従させる。JSでのスクロール追従処理は追加しない。
- API側の変更対象は `api/main.py` の日時フィルター構築ブロックのみ。`author_name`, `video_id`, `message_type` フィルターのロジックは変更しない。

---

## File Structure

- `api/main.py` — 日時範囲フィルター構築を `build_datetime_range_filters()` に切り出し、既存のインライン処理を置き換える。
- `api/conftest.py` (新規) — pytest実行時に `main.py` のimportに必要な環境変数を設定する。
- `api/tests/test_date_range.py` (新規) — `build_datetime_range_filters()` の境界値テスト。
- `api/requirements-dev.txt` (新規) — pytestなど開発用依存関係。
- `frontend/src/lib/datetimeRange.ts` (新規) — 日付+時刻をISO日時文字列に結合する純粋関数。
- `frontend/src/lib/datetimeRange.test.ts` (新規) — 上記のユニットテスト。
- `frontend/vitest.config.ts` (新規) — vitest設定。
- `frontend/package.json` — vitestの依存関係とtestスクリプトを追加。
- `frontend/src/App.tsx` — サイドバーへの時刻input追加、検索トリガー条件の変更、カードへの時計アイコン追加、前後5分表示のstate/ハンドラ、stickyバナー追加。

---

### Task 1: API — 日時範囲フィルターを純粋関数に切り出す

**Files:**
- Modify: `api/main.py:73-79`(関数追加), `api/main.py:198-214`(既存ロジック置き換え)
- Create: `api/conftest.py`
- Create: `api/tests/test_date_range.py`
- Create: `api/requirements-dev.txt`

**Interfaces:**
- Produces: `build_datetime_range_filters(date_from: Optional[str], date_to: Optional[str]) -> List[Dict[str, Any]]`(`api/main.py`からimport可能)。`search_chat_logs` 内で `filters.extend(...)` として使う。

- [ ] **Step 1: pytest環境をセットアップする**

`api/requirements-dev.txt` を作成:

```
pytest
```

`api/conftest.py` を作成(`main.py` のトップレベルで `CORS_ORIGINS.split(',')` 等、環境変数に依存した処理があるため、importより前に最低限のダミー値を設定する):

```python
import os

os.environ.setdefault("ELASTICSEARCH_HOST", "http://localhost:9200")
os.environ.setdefault("ELASTICSEARCH_API_KEY", "dummy-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("VIDEOS_INDEX_NAME", "videos")
os.environ.setdefault("CHAT_LOGS_INDEX_NAME", "chat_logs")
os.environ.setdefault("THUMBNAIL_BASE_URL", "http://localhost/thumbnails")
os.environ.setdefault("AUTHOR_ICON_BASE_URL", "http://localhost/author-icons")
os.environ.setdefault("SEARCH_TOTAL_HITS", "true")
```

venvを作成して依存関係をインストール:

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

- [ ] **Step 2: 失敗するテストを書く**

`api/tests/test_date_range.py` を作成:

```python
from datetime import datetime

from main import build_datetime_range_filters


def test_returns_empty_list_when_no_dates_given():
    assert build_datetime_range_filters(None, None) == []


def test_date_from_only_builds_gte_filter():
    filters = build_datetime_range_filters("2026-07-10T22:00:00", None)
    expected_ts = int(datetime.fromisoformat("2026-07-10T22:00:00").timestamp() * 1000)
    assert filters == [{"range": {"timestamp": {"gte": expected_ts}}}]


def test_date_to_only_builds_lte_filter_without_plus_one_day():
    filters = build_datetime_range_filters(None, "2026-07-10T23:00:00")
    expected_ts = int(datetime.fromisoformat("2026-07-10T23:00:00").timestamp() * 1000)
    assert filters == [{"range": {"timestamp": {"lte": expected_ts}}}]


def test_date_from_and_date_to_build_both_filters_in_order():
    filters = build_datetime_range_filters("2026-07-10T00:00:00", "2026-07-10T23:59:59")
    expected_from = int(datetime.fromisoformat("2026-07-10T00:00:00").timestamp() * 1000)
    expected_to = int(datetime.fromisoformat("2026-07-10T23:59:59").timestamp() * 1000)
    assert filters == [
        {"range": {"timestamp": {"gte": expected_from}}},
        {"range": {"timestamp": {"lte": expected_to}}},
    ]


def test_same_minute_from_and_to_yield_non_zero_range():
    # フロントエンドが秒を :00 / :59 に固定補完するため、同じ分を指定しても幅を持つ
    filters = build_datetime_range_filters("2026-07-10T22:00:00", "2026-07-10T22:00:59")
    gte = filters[0]["range"]["timestamp"]["gte"]
    lte = filters[1]["range"]["timestamp"]["lte"]
    assert lte > gte


def test_invalid_date_from_is_ignored():
    filters = build_datetime_range_filters("not-a-date", "2026-07-10T23:59:59")
    assert len(filters) == 1
    assert "lte" in filters[0]["range"]["timestamp"]


def test_invalid_date_to_is_ignored():
    filters = build_datetime_range_filters("2026-07-10T00:00:00", "not-a-date")
    assert len(filters) == 1
    assert "gte" in filters[0]["range"]["timestamp"]
```

- [ ] **Step 3: テストを実行して失敗を確認する**

Run: `cd api && source .venv/bin/activate && pytest tests/test_date_range.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_datetime_range_filters' from 'main'`

- [ ] **Step 4: `main.py` に関数を実装し、既存のインライン処理を置き換える**

`api/main.py:73-79` の `calculate_author_icon_url` 関数の直後(`@app.on_event("startup")` の直前)に関数を追加する。

変更前(`api/main.py:73-81`):

```python
def calculate_author_icon_url(author_channel_id: str) -> str:
    """
    authorChannelIdから投稿者アイコン画像のURLを生成する。
    """
    if not author_channel_id:
        return ""
    return f"{AUTHOR_ICON_BASE_URL}/{author_channel_id}.webp"

@app.on_event("startup")
```

変更後:

```python
def calculate_author_icon_url(author_channel_id: str) -> str:
    """
    authorChannelIdから投稿者アイコン画像のURLを生成する。
    """
    if not author_channel_id:
        return ""
    return f"{AUTHOR_ICON_BASE_URL}/{author_channel_id}.webp"

def build_datetime_range_filters(date_from: Optional[str], date_to: Optional[str]) -> List[Dict[str, Any]]:
    """
    date_from/date_toは常に完全なISO日時文字列(例 "2026-07-10T22:00:00")として渡される前提。
    date_from -> gte、date_to -> lte（そのまま、日単位の補正は行わない）。
    パースに失敗した値は無視する。
    """
    filters: List[Dict[str, Any]] = []
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            ts_from = int(dt_from.timestamp() * 1000)
            filters.append({"range": {"timestamp": {"gte": ts_from}}})
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            ts_to = int(dt_to.timestamp() * 1000)
            filters.append({"range": {"timestamp": {"lte": ts_to}}})
        except ValueError:
            pass
    return filters

@app.on_event("startup")
```

次に、`search_chat_logs` 内の既存インラインロジックを置き換える。

変更前(`api/main.py:198-215`):

```python
    # フィルターの部分
    filters = []
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            ts_from = int(dt_from.timestamp() * 1000)
            filters.append({"range": {"timestamp": {"gte": ts_from}}})
        except ValueError:
            pass # 不正な日付形式は無視
    if date_to:
        try:
            # 指定日の終わりまで含めるため、次の日の0時より小さい範囲を指定
            dt_to = datetime.fromisoformat(date_to) + timedelta(days=1)
            ts_to = int(dt_to.timestamp() * 1000)
            filters.append({"range": {"timestamp": {"lt": ts_to}}})
        except ValueError:
            pass # 不正な日付形式は無視

    if author_name:
```

変更後:

```python
    # フィルターの部分
    filters = build_datetime_range_filters(date_from, date_to)

    if author_name:
```

`timedelta` のimportは他で使用されていないため、`api/main.py:7` のimport文からも削除する。

変更前(`api/main.py:7`):

```python
from datetime import datetime, timedelta
```

変更後:

```python
from datetime import datetime
```

- [ ] **Step 5: テストを実行して成功を確認する**

Run: `cd api && source .venv/bin/activate && pytest tests/test_date_range.py -v`
Expected: 7 tests すべて PASS

- [ ] **Step 6: コミット**

```bash
git add api/main.py api/conftest.py api/tests/test_date_range.py api/requirements-dev.txt
git commit -m "$(cat <<'EOF'
refactor: Extract datetime range filter into a testable function

Replaces the date-only +1day boundary hack with a pure gte/lte range
builder that accepts full ISO datetime strings, in preparation for
time-of-day filtering on the frontend.
EOF
)"
```

---

### Task 2: フロントエンド — 日付+時刻を結合する純粋関数

**Files:**
- Create: `frontend/src/lib/datetimeRange.ts`
- Create: `frontend/src/lib/datetimeRange.test.ts`
- Create: `frontend/vitest.config.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: `combineDateTime(date: string, time: string, boundary: 'from' | 'to'): string | undefined`(`frontend/src/lib/datetimeRange.ts` からexport)。Task 3で `App.tsx` から使用する。

- [ ] **Step 1: vitest環境をセットアップする**

`frontend/package.json` の `devDependencies` に `vitest` を追加し、`scripts` に `test` を追加する。

変更前(`frontend/package.json:6-11`):

```json
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "build:staging": "tsc -b && vite build --mode staging",
    "lint": "eslint .",
    "preview": "vite preview"
  },
```

変更後:

```json
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "build:staging": "tsc -b && vite build --mode staging",
    "lint": "eslint .",
    "preview": "vite preview",
    "test": "vitest run"
  },
```

変更前(`frontend/package.json:19-20`、`devDependencies` の先頭付近):

```json
  "devDependencies": {
    "@eslint/js": "^9.36.0",
```

変更後:

```json
  "devDependencies": {
    "@eslint/js": "^9.36.0",
    "vitest": "^3.2.4",
```

`frontend/vitest.config.ts` を作成:

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
  },
});
```

依存関係をインストール:

```bash
cd frontend
npm install
```

- [ ] **Step 2: 失敗するテストを書く**

`frontend/src/lib/datetimeRange.test.ts` を作成:

```ts
import { describe, expect, it } from 'vitest';
import { combineDateTime } from './datetimeRange';

describe('combineDateTime', () => {
  it('returns undefined when date is empty', () => {
    expect(combineDateTime('', '', 'from')).toBeUndefined();
    expect(combineDateTime('', '10:00', 'to')).toBeUndefined();
  });

  it('defaults the from-boundary time to 00:00:00 when time is empty', () => {
    expect(combineDateTime('2026-07-10', '', 'from')).toBe('2026-07-10T00:00:00');
  });

  it('defaults the to-boundary time to 23:59:59 when time is empty', () => {
    expect(combineDateTime('2026-07-10', '', 'to')).toBe('2026-07-10T23:59:59');
  });

  it('fixes seconds to :00 for the from-boundary when time is provided', () => {
    expect(combineDateTime('2026-07-10', '22:00', 'from')).toBe('2026-07-10T22:00:00');
  });

  it('fixes seconds to :59 for the to-boundary when time is provided, avoiding a zero-width range when from/to share the same minute', () => {
    expect(combineDateTime('2026-07-10', '22:00', 'to')).toBe('2026-07-10T22:00:59');
  });
});
```

- [ ] **Step 3: テストを実行して失敗を確認する**

Run: `cd frontend && npm run test`
Expected: FAIL — `Cannot find module './datetimeRange'`

- [ ] **Step 4: 実装する**

`frontend/src/lib/datetimeRange.ts` を作成:

```ts
export type RangeBoundary = 'from' | 'to';

/**
 * 日付inputと任意の時刻inputを結合し、完全なISO日時文字列を返す。
 * 秒は境界の種類によらず常に固定する(from=:00, to=:59)。
 * 同じ分をFrom/Toに明示入力した場合でもゼロ幅の範囲にならないようにするため。
 */
export function combineDateTime(date: string, time: string, boundary: RangeBoundary): string | undefined {
  if (!date) return undefined;

  const seconds = boundary === 'from' ? '00' : '59';
  const hhmm = time || (boundary === 'from' ? '00:00' : '23:59');

  return `${date}T${hhmm}:${seconds}`;
}
```

- [ ] **Step 5: テストを実行して成功を確認する**

Run: `cd frontend && npm run test`
Expected: 5 tests すべて PASS

- [ ] **Step 6: コミット**

```bash
git add frontend/src/lib/datetimeRange.ts frontend/src/lib/datetimeRange.test.ts frontend/vitest.config.ts frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
feat: Add pure helper to combine date+time inputs into ISO datetime

Seconds are fixed (from=:00, to=:59) regardless of whether the time
was user-entered or defaulted, so an explicit same-minute From/To
still yields a non-zero range.
EOF
)"
```

---

### Task 3: フロントエンド — サイドバーの時刻フィルターと検索トリガー条件

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `combineDateTime` from Task 2 (`frontend/src/lib/datetimeRange.ts`)。
- Produces: `timeFrom: string`, `setTimeFrom`, `timeTo: string`, `setTimeTo`(App内state)、`hasActiveDateRange: boolean`(App内ローカル定数)。Task 4で `setTimeFrom`/`setTimeTo` を使用する。

- [ ] **Step 1: `timeFrom`/`timeTo` stateとサイドバーUIを追加する**

変更前(`frontend/src/App.tsx:81-83`):

```tsx
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [authorName, setAuthorName] = useState('');
```

変更後:

```tsx
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [timeFrom, setTimeFrom] = useState('');
  const [timeTo, setTimeTo] = useState('');
  const [authorName, setAuthorName] = useState('');
```

変更前(`frontend/src/App.tsx:90-95`):

```tsx
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [messageType, setMessageType] = useState<'all' | 'chat' | 'transcript'>('all');
  const [isCautionOpen, setIsCautionOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);

  useEffect(() => {
```

変更後:

```tsx
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [messageType, setMessageType] = useState<'all' | 'chat' | 'transcript'>('all');
  const [isCautionOpen, setIsCautionOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const hasActiveDateRange = Boolean(dateFrom && dateTo);

  useEffect(() => {
```

サイドバーの日付フィルターUIに時刻inputを追加する。

変更前(`frontend/src/App.tsx:241-266`):

```tsx
        {/* Date Filter */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-600 uppercase">投稿日</h3>
          <div>
            <label htmlFor="date-from" className="block text-sm font-medium text-slate-700 mb-1">From</label>
            <input
              type="date"
              id="date-from"
              name="date-from"
              className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="date-to" className="block text-sm font-medium text-slate-700 mb-1">To</label>
            <input
              type="date"
              id="date-to"
              name="date-to"
              className="w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
        </div>
```

変更後:

```tsx
        {/* Date Filter */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-600 uppercase">投稿日時</h3>
          <div>
            <label htmlFor="date-from" className="block text-sm font-medium text-slate-700 mb-1">From</label>
            <div className="flex gap-2">
              <input
                type="date"
                id="date-from"
                name="date-from"
                className="flex-1 min-w-0 px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
              <input
                type="time"
                id="time-from"
                name="time-from"
                className="w-28 px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={timeFrom}
                onChange={(e) => setTimeFrom(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label htmlFor="date-to" className="block text-sm font-medium text-slate-700 mb-1">To</label>
            <div className="flex gap-2">
              <input
                type="date"
                id="date-to"
                name="date-to"
                className="flex-1 min-w-0 px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
              <input
                type="time"
                id="time-to"
                name="time-to"
                className="w-28 px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                value={timeTo}
                onChange={(e) => setTimeTo(e.target.value)}
              />
            </div>
          </div>
        </div>
```

- [ ] **Step 2: `debouncedSearch` のガード条件とパラメータ組み立てを更新する**

変更前(`frontend/src/App.tsx:1-6`、import部分):

```tsx
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import VideoFilter from './components/VideoFilter';
import InquiryModal from './components/InquiryModal';
import CautionModal from './components/CautionModal';
import HelpModal from './components/HelpModal';
```

変更後:

```tsx
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import VideoFilter from './components/VideoFilter';
import InquiryModal from './components/InquiryModal';
import CautionModal from './components/CautionModal';
import HelpModal from './components/HelpModal';
import { combineDateTime } from './lib/datetimeRange';
```

変更前(`frontend/src/App.tsx:148-195`):

```tsx
  const debouncedSearch = useCallback((query: string, reset: boolean = false) => {
    if (query.trim() === '' && authorName.trim() === '' && !selectedVideoId) {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
      setTotalResults(0);
      return;
    }

    if (reset) {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
    }

    setIsLoading(true);
    const params = new URLSearchParams({
      q: query,
      from_: (reset ? 0 : from).toString(),
      exact: isExactMatch.toString(),
      sort_order: sortOrder,
      message_type: messageType,
    });
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (authorName) params.append('author_name', authorName);
    if (selectedVideoId) params.append('video_id', selectedVideoId);

    axios.get(`${API_BASE_URL}/search?${params.toString()}`)
      .then(response => {
        const { total, results } = response.data;
        if (results.length === 0) {
          setHasMore(false);
        } else {
          setSearchResults(prevResults => reset ? results : [...prevResults, ...results]);
          setFrom(prevFrom => prevFrom + results.length);
        }
        if (reset) {
          setTotalResults(total);
        }
      })
      .catch(error => {
        console.error("Error fetching search results:", error);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [from, isExactMatch, dateFrom, dateTo, authorName, selectedVideoId, sortOrder, messageType]);
```

変更後:

```tsx
  const debouncedSearch = useCallback((query: string, reset: boolean = false) => {
    if (query.trim() === '' && authorName.trim() === '' && !selectedVideoId && !hasActiveDateRange) {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
      setTotalResults(0);
      return;
    }

    if (reset) {
      setSearchResults([]);
      setFrom(0);
      setHasMore(true);
    }

    setIsLoading(true);
    const params = new URLSearchParams({
      q: query,
      from_: (reset ? 0 : from).toString(),
      exact: isExactMatch.toString(),
      sort_order: sortOrder,
      message_type: messageType,
    });
    const dateFromParam = combineDateTime(dateFrom, timeFrom, 'from');
    const dateToParam = combineDateTime(dateTo, timeTo, 'to');
    if (dateFromParam) params.append('date_from', dateFromParam);
    if (dateToParam) params.append('date_to', dateToParam);
    if (authorName) params.append('author_name', authorName);
    if (selectedVideoId) params.append('video_id', selectedVideoId);

    axios.get(`${API_BASE_URL}/search?${params.toString()}`)
      .then(response => {
        const { total, results } = response.data;
        if (results.length === 0) {
          setHasMore(false);
        } else {
          setSearchResults(prevResults => reset ? results : [...prevResults, ...results]);
          setFrom(prevFrom => prevFrom + results.length);
        }
        if (reset) {
          setTotalResults(total);
        }
      })
      .catch(error => {
        console.error("Error fetching search results:", error);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [from, isExactMatch, dateFrom, dateTo, timeFrom, timeTo, hasActiveDateRange, authorName, selectedVideoId, sortOrder, messageType]);
```

- [ ] **Step 3: デバウンス用`useEffect`の依存配列を更新する**

変更前(`frontend/src/App.tsx:197-206`):

```tsx
  useEffect(() => {
    const handler = setTimeout(() => {
      debouncedSearch(searchQuery, true); // 新しい検索なのでリセット
    }, 500); // 500msのデバウンス

    return () => {
      clearTimeout(handler);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, isExactMatch, dateFrom, dateTo, authorName, selectedVideoId, sortOrder, messageType]);
```

変更後:

```tsx
  useEffect(() => {
    const handler = setTimeout(() => {
      debouncedSearch(searchQuery, true); // 新しい検索なのでリセット
    }, 500); // 500msのデバウンス

    return () => {
      clearTimeout(handler);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, isExactMatch, dateFrom, dateTo, timeFrom, timeTo, authorName, selectedVideoId, sortOrder, messageType]);
```

- [ ] **Step 4: 「検索結果が見つかりませんでした」判定に日時範囲を含める**

変更前(`frontend/src/App.tsx:577-580`):

```tsx
              <div className="text-center py-12 text-slate-500">
                {isLoading ? '検索中...' : (searchQuery || authorName || selectedVideoId ? '検索結果が見つかりませんでした。' : '検索キーワードを入力してください。')}
              </div>
```

変更後:

```tsx
              <div className="text-center py-12 text-slate-500">
                {isLoading ? '検索中...' : (searchQuery || authorName || selectedVideoId || hasActiveDateRange ? '検索結果が見つかりませんでした。' : '検索キーワードを入力してください。')}
              </div>
```

- [ ] **Step 5: 型チェック・ビルドで検証する**

Run: `cd frontend && npm run build`
Expected: エラーなく `tsc -b && vite build` が完了する

- [ ] **Step 6: 手動確認する**

```bash
cd /home/yazzu709/utsulog
docker compose up --build
```

ブラウザで `http://localhost:3000`(または `FRONTEND_PORT` に設定されたポート)を開き:
1. 検索ワードを入力せず、サイドバーのFrom日付とTo日付のみを設定する → キーワードなしで検索が実行されることを確認する(ブラウザの開発者ツールのNetworkタブで `/search` リクエストに `date_from`/`date_to` が付与されていることを確認する)。
2. From/Toの時刻inputに同じ時刻(例 `22:00`)を入力する → リクエストの `date_from` が `...T22:00:00`、`date_to` が `...T22:00:59` になっていることを確認する。
3. 時刻を空のままにする → `date_from` が `...T00:00:00`、`date_to` が `...T23:59:59` になっていることを確認する。

- [ ] **Step 7: コミット**

```bash
git add frontend/src/App.tsx
git commit -m "$(cat <<'EOF'
feat: Add optional time-of-day inputs to the post-datetime filter

From/To now accept an optional time alongside the existing date, and
a complete date+time range triggers search without requiring a
keyword.
EOF
)"
```

---

### Task 4: フロントエンド — カードの「前後5分を表示」コマンド

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `timeFrom`/`setTimeFrom`/`timeTo`/`setTimeTo`(Task 3)、`SearchResult` 型、既存の `dateFrom`/`setDateFrom`/`dateTo`/`setDateTo`/`searchQuery`/`setSearchQuery`/`authorName`/`setAuthorName`/`messageType`/`setMessageType`/`selectedVideoId`/`setSelectedVideoId`/`sortOrder`/`setSortOrder` state。
- Produces: `showContextAround(result: SearchResult): void`、`restoreSnapshot(): void`、`filterSnapshot: SearchFiltersSnapshot | null` state。

- [ ] **Step 1: スナップショット型とstate、日時フォーマットのヘルパーを追加する**

変更前(`frontend/src/App.tsx:19-33`、`SearchResult` interface直後):

```tsx
// APIから返される検索結果の型定義
interface SearchResult {
  id: string;
  videoId: string;
  datetime: string;
  timestampSec: number;
  elapsedTime: string;
  author: string;
  message: string;
  videoTitle: string;
  thumbnailUrl: string;
  authorChannelId: string;
  authorIconUrl: string;
  type?: string;
}
```

変更後:

```tsx
// APIから返される検索結果の型定義
interface SearchResult {
  id: string;
  videoId: string;
  datetime: string;
  timestampSec: number;
  elapsedTime: string;
  author: string;
  message: string;
  videoTitle: string;
  thumbnailUrl: string;
  authorChannelId: string;
  authorIconUrl: string;
  type?: string;
}

// 「前後5分を表示」実行前の検索条件を保持するためのスナップショット
interface SearchFiltersSnapshot {
  searchQuery: string;
  dateFrom: string;
  timeFrom: string;
  dateTo: string;
  timeTo: string;
  authorName: string;
  selectedVideoId: string | null;
  messageType: 'all' | 'chat' | 'transcript';
  sortOrder: 'asc' | 'desc';
}
```

変更前(`frontend/src/App.tsx:54-64`、`formatDate` ヘルパー):

```tsx
// timestamp (ms) を yyyy-mm-dd HH:MM:SS 形式に変換するヘルパー関数
const formatDate = (timestamp: number): string => {
  const date = new Date(timestamp);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const HH = String(date.getHours()).padStart(2, '0');
  const MM = String(date.getMinutes()).padStart(2, '0');
  const SS = String(date.getSeconds()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd} ${HH}:${MM}:${SS}`;
};
```

変更後(直後にヘルパーを追加):

```tsx
// timestamp (ms) を yyyy-mm-dd HH:MM:SS 形式に変換するヘルパー関数
const formatDate = (timestamp: number): string => {
  const date = new Date(timestamp);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const HH = String(date.getHours()).padStart(2, '0');
  const MM = String(date.getMinutes()).padStart(2, '0');
  const SS = String(date.getSeconds()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd} ${HH}:${MM}:${SS}`;
};

// timestamp (ms) を date input用の yyyy-mm-dd 形式に変換するヘルパー関数
const formatDateInputValue = (timestamp: number): string => {
  const date = new Date(timestamp);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
};

// timestamp (ms) を time input用の HH:MM 形式に変換するヘルパー関数
const formatTimeInputValue = (timestamp: number): string => {
  const date = new Date(timestamp);
  const HH = String(date.getHours()).padStart(2, '0');
  const MM = String(date.getMinutes()).padStart(2, '0');
  return `${HH}:${MM}`;
};

// date input(yyyy-mm-dd)とtime input(HH:MM)を「MM/DD HH:MM」表示用にまとめるヘルパー関数
const formatRangeLabel = (date: string, time: string): string => {
  if (!date) return '';
  const [, month, day] = date.split('-');
  return time ? `${month}/${day} ${time}` : `${month}/${day}`;
};
```

`filterSnapshot` stateを追加する。

変更前(`frontend/src/App.tsx:92-96`、Task 3で追加した `hasActiveDateRange` の直後):

```tsx
  const [isCautionOpen, setIsCautionOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const hasActiveDateRange = Boolean(dateFrom && dateTo);

  useEffect(() => {
```

変更後:

```tsx
  const [isCautionOpen, setIsCautionOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const hasActiveDateRange = Boolean(dateFrom && dateTo);
  const [filterSnapshot, setFilterSnapshot] = useState<SearchFiltersSnapshot | null>(null);

  useEffect(() => {
```

- [ ] **Step 2: `showContextAround`/`restoreSnapshot` ハンドラを実装する**

無限スクロール用`useEffect`(`frontend/src/App.tsx:208-226`)の直後、`return (` の直前にハンドラを追加する。

変更前(`frontend/src/App.tsx:226-228`):

```tsx
  }, [isLoading, hasMore, searchQuery, debouncedSearch]);

  return (
```

変更後:

```tsx
  }, [isLoading, hasMore, searchQuery, debouncedSearch]);

  const showContextAround = (result: SearchResult) => {
    setFilterSnapshot({
      searchQuery,
      dateFrom,
      timeFrom,
      dateTo,
      timeTo,
      authorName,
      selectedVideoId,
      messageType,
      sortOrder,
    });

    const FIVE_MINUTES_MS = 5 * 60 * 1000;
    const windowStart = result.timestampSec - FIVE_MINUTES_MS;
    const windowEnd = result.timestampSec + FIVE_MINUTES_MS;

    setSearchQuery('');
    setAuthorName('');
    setMessageType('all');
    setSelectedVideoId(result.videoId);
    setDateFrom(formatDateInputValue(windowStart));
    setTimeFrom(formatTimeInputValue(windowStart));
    setDateTo(formatDateInputValue(windowEnd));
    setTimeTo(formatTimeInputValue(windowEnd));
    setSortOrder('asc');
  };

  const restoreSnapshot = () => {
    if (!filterSnapshot) return;
    setSearchQuery(filterSnapshot.searchQuery);
    setDateFrom(filterSnapshot.dateFrom);
    setTimeFrom(filterSnapshot.timeFrom);
    setDateTo(filterSnapshot.dateTo);
    setTimeTo(filterSnapshot.timeTo);
    setAuthorName(filterSnapshot.authorName);
    setSelectedVideoId(filterSnapshot.selectedVideoId);
    setMessageType(filterSnapshot.messageType);
    setSortOrder(filterSnapshot.sortOrder);
    setFilterSnapshot(null);
  };

  return (
```

- [ ] **Step 3: カードのelapsedTimeバッジの下に時計アイコンを追加する**

変更前(`frontend/src/App.tsx:553-556`):

```tsx
                          <span className="text-sm font-medium text-slate-600 bg-slate-100 px-3 py-1 rounded-full">
                            {formatTimestamp(result.elapsedTime)}
                          </span>
```

変更後:

```tsx
                          <div className="flex flex-col items-center space-y-1">
                            <span className="text-sm font-medium text-slate-600 bg-slate-100 px-3 py-1 rounded-full">
                              {formatTimestamp(result.elapsedTime)}
                            </span>
                            <button
                              onClick={() => showContextAround(result)}
                              className="text-slate-400 hover:text-blue-600 transition-colors"
                              title="前後5分を表示"
                              aria-label="前後5分を表示"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                              </svg>
                            </button>
                          </div>
```

- [ ] **Step 4: sticky なバナーを検索結果セクションの直前に追加する**

変更前(`frontend/src/App.tsx:506-511`):

```tsx
          {/* Search Results */}
          <section className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold text-slate-800">
                検索結果 ({totalResults.toLocaleString()}件)
              </h3>
```

変更後:

```tsx
          {filterSnapshot && (
            <div className="sticky top-0 z-10 mb-4 px-4 py-3 bg-blue-50/95 border border-blue-200 rounded-md flex items-center justify-between gap-4">
              <p className="text-sm text-blue-800">
                期間表示中: {formatRangeLabel(dateFrom, timeFrom)} 〜 {formatRangeLabel(dateTo, timeTo)}
              </p>
              <button
                onClick={restoreSnapshot}
                className="text-sm font-medium text-blue-700 hover:text-blue-900 underline whitespace-nowrap"
              >
                元の検索に戻る
              </button>
            </div>
          )}

          {/* Search Results */}
          <section className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold text-slate-800">
                検索結果 ({totalResults.toLocaleString()}件)
              </h3>
```

- [ ] **Step 5: 型チェック・ビルドで検証する**

Run: `cd frontend && npm run build`
Expected: エラーなく `tsc -b && vite build` が完了する

- [ ] **Step 6: 手動確認する**

```bash
cd /home/yazzu709/utsulog
docker compose up --build
```

ブラウザで `http://localhost:3000` を開き、何らかのキーワードで検索して結果カードを表示させたうえで:
1. カードのelapsedTimeバッジ下の時計アイコンをタップする → 検索ワードが空になり、サイドバーのFrom/Toにそのカードの投稿日時の±5分が反映され、同じ動画のチャット/実況が時系列順(古い→新しい)に表示されることを確認する。
2. 画面をスクロールしても、上部の「期間表示中」バナーが画面上部に留まる(sticky)ことを確認する。
3. サイドバーのTo側の時刻を手動で数分後ろにずらす → バナーの表示期間が更新され、再検索されることを確認する。
4. 「元の検索に戻る」をタップする → 手順1の前の検索条件(キーワード・フィルター)に戻ることを確認する。

- [ ] **Step 7: コミット**

```bash
git add frontend/src/App.tsx
git commit -m "$(cat <<'EOF'
feat: Add "show ±5min" command to search result cards

Tapping the clock icon under a card's elapsed-time badge scopes the
search to the same video, ±5 minutes around that message, clearing
the keyword/author/type filters so the surrounding context is
visible. A sticky banner shows the active window and lets the user
restore the prior search.
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- 投稿日→投稿日時への拡張、From/To時刻選択(スマホ向け最小UI): Task 3。
- From/To投稿日時が揃ったらキーワードなしでも検索: Task 3 Step 2/4。
- カードから「前後5分のチャットを表示」(plan2: 時計アイコン): Task 4。
- 秒固定補完によるゼロ幅回避: Task 1(API側テスト)・Task 2(フロント純粋関数)。
- 同一動画内に限定、他フィルターリセット、sortOrder=asc: Task 4 Step 2。
- バナーの汎用文言・sticky追従・元の検索へ復帰: Task 4 Step 4。
- APIの+1日ハック廃止(gte/lte): Task 1。

**Placeholder scan:** なし(すべてのステップに具体的なコード・コマンドを記載済み)。

**Type consistency:** `SearchFiltersSnapshot` のプロパティ名(`searchQuery`, `dateFrom`, `timeFrom`, `dateTo`, `timeTo`, `authorName`, `selectedVideoId`, `messageType`, `sortOrder`)は `showContextAround`/`restoreSnapshot` 双方で一致。`combineDateTime(date, time, boundary)` のシグネチャはTask 2の実装とTask 3の呼び出し箇所で一致。`build_datetime_range_filters(date_from, date_to)` はTask 1のテストと実装で一致。
