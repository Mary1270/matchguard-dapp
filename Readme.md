# MatchGuard — Adversarial Sports Event Settlement Intelligent Contract

## چرا این پروژه، و چرا از ScoreSettle قوی‌تره

ScoreSettle یه سؤال ساده جواب می‌داد: «نتیجه‌ی بازی چند-چند شد؟». MatchGuard یه لایه‌ی معماری بالاتره: کل **وضعیت** یه رویداد ورزشی رو به‌صورت قابل‌حل‌وفصل و ضدِ‌دستکاری تعیین می‌کنه — نه فقط اسکور نهایی، بلکه اینکه آیا بازی اصلاً برگزار شد، آیا لغو/تعویق/نیمه‌تموم شد، آیا منابع با هم اختلاف دارن، و اگه اجماعی شکل نگرفت چه بلایی سر stake میاد.

مهم‌تر از همه: MatchGuard مستقیماً به تنها ایراد مشخصی که Steward رو ScoreSettle مطرح کرده بود جواب می‌ده — **قفل‌شدن زودهنگام منابع (first-resolver lock)** — و همین درس رو یه بار دیگه، مستقل، برای مکانیزم challenge هم پیاده کرده.

## معماری — هشت رکن

1. **Canonical Event Identity** — فیکسچر با `sport` + `competition` + `home_team` + `away_team` + `scheduled_start` قفل می‌شه؛ هر منبع باید یه چک `EVENT_MATCH` رو رد کنه تا معتبر باشه، نه فقط اسم تیم‌ها.
2. **Locked Source Set، فقط بعد از evidence واقعی** — دقیقاً برخلاف مشکل ScoreSettle: مجموعه‌ی منابع فقط وقتی قفل می‌شه که واقعاً حداقل تعداد لازم evidence مستقل و باکیفیت جمع بشه؛ تلاش ناموفق چیزی رو قفل نمی‌کنه و match باز و قابل‌تلاش‌مجدد می‌مونه.
3. **Multi-Source Semantic Consensus دو-مرحله‌ای** — اول اجماع روی STATUS (Final/Postponed/Cancelled/Abandoned)، بعد فقط اگه STATUS=Final بود، اجماع روی RESULT. اختلاف در هرکدوم → Disputed، evidence ناکافی → Indeterminate.
4. **Two-Phase Optimistic Resolution** — پیشنهاد اول (`propose_resolution`) همیشه provisional هست و یه پنجره‌ی challenge باز می‌شه، حتی اگه verdict اولیه قطعی به نظر برسه.
5. **Evidence-Based Challenge** — چالش باید یه URL واقعی بده، فقط از طرف party_a/party_b، فقط تو پنجره‌ی زمانی، و محدود به تعداد raunds مشخص.
6. **Result Versioning / Immutable History** — هر propose و هر challenge (چه قبول چه رد) به‌صورت append-only با version و timestamp ثبت می‌شه؛ هیچ‌چیزی هیچ‌وقت silent rewrite نمی‌شه.
7. **Three-Way Settlement همیشه Terminal** — فقط سه خروجی نهایی ممکنه: `party_a_wins` / `party_b_wins` / `refund`. Draw، Postponed، Cancelled، Abandoned، Disputed، و Indeterminate همه به `refund` می‌رن — هیچ‌وقت یه حالت «معلق» باقی نمی‌مونه.
8. **Timeout Recovery — بدون قفل دائمی پول** — هر مسیر تو state machine یه خروج permissionless و زمان‌بندی‌شده داره: `expire_match` برای match‌های هیچ‌وقت‌accept‌نشده یا هیچ‌وقت‌propose‌نشده، و `finalize_match` برای هر match که به مرحله‌ی proposed رسیده (حتی اگه روی Disputed/Indeterminate گیر کرده باشه).

## مقایسه با ScoreSettle

| | ScoreSettle | MatchGuard |
|---|---|---|
| تسویه | اسکور نهایی | کل وضعیت رویداد (Final/Postponed/Cancelled/Abandoned/Disputed/Indeterminate) |
| Party binding | آدرس‌محور | آدرس‌محور + canonical event binding |
| زمان‌بندی | یه deadline | پنجره‌ی propose + پنجره‌ی challenge مستقل |
| اجماع | یه‌مرحله‌ای | دو-مرحله‌ای (status سپس result) |
| ثبت نتیجه | مقدار نهایی | تاریخچه‌ی نسخه‌دار immutable |
| تسویه | Win/Lose | Win/Lose/Refund — همیشه terminal |
| مکانیزم اعتراض | — | Challenge evidence-based |
| محافظت از fund | فقط expiry | expiry **و** finalize permissionless روی هر proposed match |

## اثبات کارکرد روی چین واقعی (نه فقط تست آفلاین)

قرارداد دیپلوی و روی یه بازی واقعی (Mainz 05 vs Eintracht Frankfurt، بوندسلیگا، ۱۲ سپتامبر ۲۰۲۶، نتیجه‌ی نهایی ۱–۳) تست شد:

- **Contract:** `0xA98b5BdD53a91533214103aAfbC6687Da8239Bc4`
- **Deploy tx:** `0x188af5ff831b5a0b948fccc53b7284c3f2220e955f5c6812140b5622fd9ed2dc`
- **create_match tx:** `0xe733047fc3885c8497b9b468d4d9ed6e404dcb01fdb82683859755e7dda3825c` → `match_id: "0"`
- **accept_match tx:** `0xc3ea5c534e9a762cc07779fb3849e2383c3fbbc622609f20c7aabb929be496aa` → status → `open`
- **propose_resolution (تلاش اول، ناموفق) tx:** `0x7ab76f896712e67e839552f8ab8f730429f85796eb3cf22aabcc0183ab00bc64` — با ۲ منبع (ESPN + BBC). ESPN با `quality_flag: "event_mismatch"` رد شد (LLM نتونست فیکسچر رو با اطمینان تأیید کنه)، پس فقط ۱ منبع معتبر موند — کمتر از حداقل لازم. **نتیجه: هیچی قفل نشد، status همچنان `"open"` موند.** این دقیقاً همون رفتاریه که رکن #۲ رو اثبات می‌کنه: بدون evidence کافی، هیچ منبعی — حتی اولی — قفل نمی‌شه.
- **propose_resolution (تلاش دوم، موفق) tx:** `0x9f06dc0ee5f96f599df256dc8a6cb78f01e31485e2094120282e8be0b7cd29b5` — با ۳ منبع (ESPN + BBC + Sofascore)، هر سه `quality_flag: "ok"` و `AwayWin`. نتیجه: `status → "proposed"`, `proposed_verdict: "AwayWin"`, `proposed_settlement: "party_b_wins"`, `challenge_deadline` ست شد، اولین entry تو `resolution_history` (version 1, trigger: "proposed") ثبت شد.
- **finalize_match tx:** `0xa384ea236972232dc9740dc76cd85fe4ef5d4196f0b27008031fe463ee280c37` — بعد از بسته‌شدن پنجره‌ی challenge: `status → "finalized"`, `final_verdict: "AwayWin"`, `settlement_outcome: "party_b_wins"`, دومین entry تو `resolution_history` (trigger: "finalized").
- **get_match / get_role / total_matches:** همه به‌درستی جواب دادن (`party_a`, `none`, `1`).

منابع evidence استفاده‌شده:
- ESPN: `https://www.espn.com/soccer/match/_/gameId/401884794/eintracht-frankfurt-mainz`
- BBC: `https://www.bbc.com/sport/football/live/ckvgy147z1e5t`
- Sofascore: `https://www.sofascore.com/football/match/eintracht-frankfurt-1-fsv-mainz-05/gbbszdb`

## تست آفلاین

۴۶ تست pytest (party binding و timing، URL/domain parsing، two-stage aggregation logic، و end-to-end کامل شامل سناریوی challenge که یه verdict را از Disputed به یه نتیجه‌ی قطعی و برعکس تبدیل می‌کنه) — همه پاس.

## Repository / Frontend

- GitHub repo: **[لینک ریپو رو اینجا بذار]**
- GitHub Pages (frontend زنده): **[لینک صفحه رو اینجا بذار]**
- GenLayer Explorer: `https://explorer-studio.genlayer.com/address/0xA98b5BdD53a91533214103aAfbC6687Da8239Bc4`
