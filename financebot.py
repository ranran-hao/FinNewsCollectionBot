# 福生无量天尊 - 财经新闻智能推送（早间全球/晚间亚洲）
from openai import OpenAI
import feedparser
import requests
from newspaper import Article
from datetime import datetime
import time
import pytz
import os

# ============================================================
# 配置区
# ============================================================

# OpenAI API Key
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("环境变量 OPENAI_API_KEY 未设置，请在Github Actions中设置此变量！")

# 从环境变量获取 Server酱 SendKeys
server_chan_keys_env = os.getenv("SERVER_CHAN_KEYS")
if not server_chan_keys_env:
    raise ValueError("环境变量 SERVER_CHAN_KEYS 未设置，请在Github Actions中设置此变量！")
server_chan_keys = server_chan_keys_env.split(",")

openai_client = OpenAI(api_key=openai_api_key, base_url="https://api.deepseek.com/v1")

# ============================================================
# 早间 RSS 源（9:00 运行）— 以全球市场为主
# ============================================================
morning_feeds = {
    "🌏 全球宏观": {
        "BBC全球经济": "http://feeds.bbci.co.uk/news/business/rss.xml",
        "路透社全球商业": "https://feeds.reuters.com/reuters/businessNews",
    },
    "💰 贵金属/能源/商品": {
        "ZeroHedge": "https://feeds.feedburner.com/zerohedge/feed",
        "ETF Trends": "https://www.etftrends.com/feed/",
    },
    "🤖 AI/科技": {
        "36氪": "https://36kr.com/feed",
        "TechCrunch": "https://techcrunch.com/feed/",
    },
    "📈 美股市场": {
        "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    },
}

# ============================================================
# 晚间 RSS 源（18:00 运行）— 以亚洲市场为主
# ============================================================
evening_feeds = {
    "🇨🇳 中国财经": {
        "华尔街见闻": "https://dedicated.wallstreetcn.com/rss.xml",
        "东方财富": "http://rss.eastmoney.com/rss_partener.xml",
        "36氪快讯": "https://36kr.com/feed-newsflash",
        "虎嗅": "https://www.huxiu.com/rss/0.xml",
    },
    "💼 创投/一级市场": {
        "36氪创投": "https://36kr.com/feed",
        "投资界": "https://www.pedaily.cn/rss.xml",
    },
    "🇭🇰 港股/亚太": {
        "香港经济日报": "https://www.hket.com/rss/china",
        "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    },
}

# ============================================================
# 早间提示词 — 全球市场 + 贵金属/能源 + AI动态 + 科普
# ============================================================
MORNING_PROMPT = """你是一位面向普通投资者的财经科普编辑。请根据以下新闻内容完成两个部分：

**一、新闻总结**
- 按重要程度从高到低排列，重要新闻展开说明，次要新闻一句话带过
- 每条新闻如果原始内容中包含具体时间，必须标明发生时间（如"6月16日早8点"），如果原文没有具体时间则不要编造
- 重点关注以下领域：
  1. 全球市场动态（美股、欧股、亚太盘前等）
  2. 贵金属价格及近期走势对比（如有黄金、白银相关新闻）
  3. 能源与原油价格动态（如有）
  4. AI 大公司新闻（OpenAI、Google、微软、英伟达、Meta等如有相关动态）
- 只报道新闻中明确提到的内容，不要编造数据、价格或事件

**二、科普时间**
- 从今日新闻中挑出 2-3 个最重要的专业概念或术语
- 用通俗语言解释：这个概念是什么？为什么它重要？对普通人意味着什么？
- 科普要和新闻自然衔接，不要生硬插入
- 只科普确实重要且读者可能不熟悉的概念，常见词汇不用解释

整体风格要求：信息量大但不啰嗦，像一位懂行的朋友在跟你聊财经，而不是干巴巴的研究报告。"""

# ============================================================
# 晚间提示词 — 亚洲市场 + 创投动态 + 科普
# ============================================================
EVENING_PROMPT = """你是一位面向普通投资者的财经科普编辑。请根据以下新闻内容完成两个部分：

**一、新闻总结**
- 按重要程度从高到低排列，重要新闻展开说明，次要新闻一句话带过
- 每条新闻如果原始内容中包含具体时间，必须标明发生时间（如"6月16日下午3点"），如果原文没有具体时间则不要编造
- 重点关注以下领域：
  1. 亚洲/中国市场动态（A股、港股、政策等）
  2. 一级市场大新闻（IPO、重大融资、并购等）
  3. 创投圈重大事件（知名机构动向、明星创业公司融资等）
  4. 重要产业政策和监管动态
- 只报道新闻中明确提到的内容，不要编造数据、金额或事件

**二、科普时间**
- 从今日新闻中挑出 2-3 个最重要的专业概念或术语
- 用通俗语言解释：这个概念是什么？为什么它重要？对普通人意味着什么？
- 科普要和新闻自然衔接，不要生硬插入
- 只科普确实重要且读者可能不熟悉的概念，常见词汇不用解释

整体风格要求：信息量大但不啰嗦，像一位懂行的朋友在跟你聊财经，而不是干巴巴的研究报告。"""


# ============================================================
# 工具函数
# ============================================================

def get_beijing_time():
    return datetime.now(pytz.timezone("Asia/Shanghai"))


def get_period():
    """根据北京时间判断早间还是晚间"""
    hour = get_beijing_time().hour
    return "morning" if hour < 14 else "evening"


def get_period_label(period):
    return "☀️ 早间" if period == "morning" else "🌙 晚间"


def today_date():
    return get_beijing_time().date()


def fetch_article_text(url):
    try:
        print(f"📰 正在爬取文章内容: {url}")
        article = Article(url)
        article.download()
        article.parse()
        text = article.text[:1500]
        if not text:
            print(f"⚠️ 文章内容为空: {url}")
        return text
    except Exception as e:
        print(f"❌ 文章爬取失败: {url}，错误: {e}")
        return "（未能获取文章正文）"


def fetch_feed_with_headers(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    return feedparser.parse(url, request_headers=headers)


def fetch_feed_with_retry(url, retries=3, delay=5):
    for i in range(retries):
        try:
            feed = fetch_feed_with_headers(url)
            if feed and hasattr(feed, 'entries') and len(feed.entries) > 0:
                return feed
        except Exception as e:
            print(f"⚠️ 第 {i+1} 次请求 {url} 失败: {e}")
            time.sleep(delay)
    print(f"❌ 跳过 {url}, 尝试 {retries} 次后仍失败。")
    return None


def fetch_rss_articles(rss_feeds, max_per_source=5):
    """抓取所有 RSS 源的文章"""
    news_data = {}
    analysis_text = ""

    for category, sources in rss_feeds.items():
        category_content = ""
        for source, url in sources.items():
            print(f"📡 正在获取 {source} 的 RSS 源: {url}")
            feed = fetch_feed_with_retry(url)
            if not feed:
                print(f"⚠️ 无法获取 {source} 的 RSS 数据")
                continue
            print(f"✅ {source} RSS 获取成功，共 {len(feed.entries)} 条新闻")

            articles = []
            for entry in feed.entries[:max_per_source]:
                title = entry.get('title', '无标题')
                link = entry.get('link', '') or entry.get('guid', '')
                if not link:
                    print(f"⚠️ {source} 的新闻 '{title}' 没有链接，跳过")
                    continue

                article_text = fetch_article_text(link)
                analysis_text += f"【{title}】\n{article_text}\n\n"

                print(f"🔹 {source} - {title} 获取成功")
                articles.append(f"- [{title}]({link})")

            if articles:
                category_content += f"### {source}\n" + "\n".join(articles) + "\n\n"

        news_data[category] = category_content

    return news_data, analysis_text


def summarize(text, prompt):
    """调用 AI 生成新闻总结+科普"""
    completion = openai_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    )
    return completion.choices[0].message.content.strip()


def send_to_wechat(title, content):
    """通过 Server酱 推送到微信"""
    for key in server_chan_keys:
        url = f"https://sctapi.ftqq.com/{key}.send"
        data = {"title": title, "desp": content}
        response = requests.post(url, data=data, timeout=10)
        if response.ok:
            print(f"✅ 推送成功: {key}")
        else:
            print(f"❌ 推送失败: {key}, 响应：{response.text}")


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    today_str = today_date().strftime("%Y-%m-%d")
    period = get_period()
    period_label = get_period_label(period)

    print(f"🕐 当前为北京时间 {get_beijing_time().strftime('%H:%M')}，模式：{period_label}")

    # 根据时段选择新闻源和提示词
    if period == "morning":
        rss_feeds = morning_feeds
        prompt = MORNING_PROMPT
        period_desc = "全球市场 | 贵金属/能源 | AI动态"
    else:
        rss_feeds = evening_feeds
        prompt = EVENING_PROMPT
        period_desc = "亚洲/中国市场 | 创投/一级市场"

    # 抓取新闻
    articles_data, analysis_text = fetch_rss_articles(rss_feeds, max_per_source=5)

    # AI 生成总结+科普
    summary = summarize(analysis_text, prompt)

    # 组装最终推送内容
    final_summary = f"📅 **{today_str} {period_label}财经日报**\n\n"
    final_summary += f"📡 本期重点：{period_desc}\n\n"
    final_summary += f"---\n\n{summary}\n\n---\n\n"
    final_summary += "📎 **新闻链接**\n\n"
    for category, content in articles_data.items():
        if content.strip():
            final_summary += f"**{category}**\n{content}\n\n"

    # 推送
    send_to_wechat(title=f"📌 {today_str} {period_label}财经日报", content=final_summary)
