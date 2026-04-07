# Forge Engine Integration — Supabase Tables & Query Patterns

> Script Factory đọc dữ liệu từ Forge Engine (Intelligence Forge) để gợi ý topics.
> Forge Engine chạy RIÊNG BIỆT (project khác), chỉ SHARE data qua Supabase.

## Supabase Project
- **URL:** `https://bksqlgwotvpabksnynbo.supabase.co`
- **Dùng chung** cho cả Video Factory, Doodle Factory, Forge Engine, Script Factory

---

## Tables cần đọc (READ-ONLY — KHÔNG sửa schema)

### 1. `content_queue` — Topics đã scored bởi Forge Engine
```sql
-- Schema
id UUID PRIMARY KEY
catalyst_session_id UUID
insight_raw TEXT          -- Raw insight từ Forge
suggested_topic TEXT      -- Topic gợi ý (tiếng Việt) ← DÙNG CÁI NÀY
suggested_hook TEXT       -- Hook gợi ý (có thể null)
content_type TEXT         -- "viral" | "ai" | "tuhoc" ← FILTER BẰNG CÁI NÀY
brain2_concepts TEXT[]    -- Array vault note paths liên quan
brain2_stories TEXT[]     -- Array vault story paths
total_score INT           -- Điểm tổng (sort by DESC) ← SORT BẰNG CÁI NÀY
status TEXT               -- "queued" | "writing" | "published"
priority INT
created_at TIMESTAMPTZ
```

**Query pattern:**
```python
# Lấy top topics cho channel AI
result = supabase.table("content_queue") \
    .select("id, suggested_topic, suggested_hook, brain2_concepts, total_score") \
    .eq("status", "queued") \
    .eq("content_type", "ai") \
    .order("total_score", desc=True) \
    .limit(10) \
    .execute()
```

**Sample data (24 rows hiện có):**
```
"Quản lý hỗn loạn AI Agent: Từ OpenClaw đến hạ tầng tổ chức Zero-Human Company"
"Chiến lược đóng vườn của Anthropic: Tại sao Claude Pro/Max không còn là cửa sau..."
"Kỷ nguyên AI-native development: Từ ý tưởng đến MVP trong 90 ngày..."
```

### 2. `forge_articles` — Tin AI đã thu thập & summarized
```sql
-- Schema
id UUID PRIMARY KEY
source_name TEXT          -- "Google AI Blog", "Andrew Ng Newsletter"
source_category TEXT      -- "rss" | "youtube" | "x_kol" | "github" | "research"
title TEXT                -- Title gốc (English)
title_vi TEXT             -- Title dịch (Việt) ← DÙNG CÁI NÀY
url TEXT
original_content TEXT     -- Nội dung gốc (max 5000 chars)
summary_vi TEXT           -- Tóm tắt tiếng Việt ← DÙNG CÁI NÀY LÀM CONTEXT
published_at TIMESTAMPTZ
collected_at TIMESTAMPTZ
is_read BOOLEAN
is_bookmarked BOOLEAN
```

**Query pattern:**
```python
# Lấy context từ articles liên quan (khi topic có source_ref từ forge)
result = supabase.table("forge_articles") \
    .select("title_vi, summary_vi, source_category") \
    .in_("id", article_ids) \
    .execute()
```

### 3. `daily_insights` — Bản tin AI hàng ngày
```sql
-- Schema
id UUID PRIMARY KEY
insight_date DATE         -- YYYY-MM-DD (unique)
highlight_summary TEXT    -- 3-5 câu tổng hợp trends
must_read_ids UUID[]      -- Array forge_articles IDs đáng đọc
key_trends JSONB          -- [{"trend": "...", "count": N, "category": "..."}]
source_stats JSONB        -- {"rss": 50, "youtube": 10, ...}
total_articles INT
generated_at TIMESTAMPTZ
```

**Query pattern:**
```python
# Lấy insight hôm nay cho trending topics
today = datetime.now().strftime("%Y-%m-%d")
result = supabase.table("daily_insights") \
    .select("*") \
    .eq("insight_date", today) \
    .single() \
    .execute()
```

---

## Tables cần WRITE (Script Factory owns)

### 4. `tpe_script_topics` — MỚI, TẠO TRONG MIGRATION
### 5. `tpe_scripts` — MỚI, TẠO TRONG MIGRATION

Schema chi tiết xem trong handoff.md Task 1.

---

## Brain2 Vault Search — Supabase RPC

```python
# Semantic search trong Brain2 vault (1628 chunks)
def search_vault(query: str, match_count: int = 5) -> list[dict]:
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"query_text": query, "match_count": match_count}
    
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/rpc/match_memory_notes",
        headers=headers, json=payload, timeout=15
    )
    return r.json() if r.status_code == 200 else []
```

**Response format:**
```json
[
  {
    "title": "concept-power-law",
    "content": "## Power Law trong kiếm tiền\n\n80% thu nhập đến từ 20% effort...",
    "similarity": 0.85
  }
]
```
