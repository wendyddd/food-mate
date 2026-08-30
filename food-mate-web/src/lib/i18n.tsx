/**
 * Frontend i18n: locale type, message tables, preference persistence, and React Context.
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "en" | "zh";

const STORAGE_KEY = "foodmate_locale";

/** English copy */
const en = {
  "common.confirm": "Confirm",
  "common.cancel": "Cancel",
  "common.close": "Close",
  "common.delete": "Delete",
  "common.edit": "Edit",
  "common.save": "Save",
  "common.saving": "Saving...",
  "common.rename": "Rename",
  "common.view": "View",
  "common.online": "Online",
  "common.entries": "entries",
  "common.entry": "entry",
  "common.language": "Language",
  "common.lang.en": "English",
  "common.lang.zh": "中文",

  "login.subtitle": "Sign in to your FoodMate account",
  "login.uid": "User ID",
  "login.uidPlaceholder": "Enter your uid",
  "login.password": "Password",
  "login.passwordPlaceholder": "Enter your password",
  "login.submit": "Sign in",
  "login.submitting": "Signing in...",
  "login.error": "Invalid username or password. Please try again.",

  "nav.chat": "Chat",
  "nav.memory": "Memory",
  "nav.memorySub": "System",
  "nav.newChat": "New Chat",
  "nav.recent": "Recent",
  "nav.expand": "Expand sidebar",
  "nav.collapse": "Collapse sidebar",
  "nav.signOut": "Sign out",
  "nav.deleteSession": "Delete session",
  "nav.deleteSessionMsg": 'Delete session "{title}"? This cannot be undone.',

  "chat.greeting": "Hi, I'm FoodMate",
  "chat.intro": "Your home cooking helper — try",
  "chat.introHint": "What should I cook tonight?",
  "chat.hint1": "What should I cook tonight?",
  "chat.hint2": "Suggest an easy home-cooked dish",
  "chat.hint3": "I only have eggs and tomatoes — what can I make?",
  "chat.hint4": "What dishes are good for kids?",
  "chat.hint5": "Help me plan dinners for a week",
  "chat.hint6": "What should I eat while cutting fat?",
  "chat.hint7": "Quick dishes I can finish in 15 minutes",
  "chat.hint8": "I only have potatoes and meat — any ideas?",
  "chat.hint9": "Recommend a hearty rice-friendly dish",
  "chat.hint10": "Light summer salads or cold dishes?",
  "chat.hint11": "Teach me a hard-to-fail braised pork belly",
  "chat.hint12": "How to balance nutrition for a vegetarian week?",
  "chat.hint13": "What dishes work well for lunchboxes?",
  "chat.hint14": "What is gentle on the stomach when I'm sick?",
  "chat.hint15": "What can I make with an air fryer?",
  "chat.hint16": "Dishes good for hosting guests",
  "chat.hint17": "Simple recipes with few cutting steps",
  "chat.hint18": "Budget-friendly meal plan for one week",
  "chat.hint19": "Recommend a spicy Sichuan home-style dish",
  "chat.hint20": "Breakfast ideas beyond porridge and buns",
  "chat.hint21": "How to turn leftover rice into a good meal?",
  "chat.hint22": "Any beginner-friendly dessert recipes?",
  "chat.hint23": "What should I eat for dinner when bulking?",
  "chat.hint24": "Suggest a two-person dinner menu",
  "chat.hint25": "One-pot meals that are easy to clean up",
  "chat.hint26": "How do I cook fish without the fishy smell?",
  "chat.hint27": "Recommend a soup for a rainy evening",
  "chat.hint28": "I have chicken breast — healthy recipes?",
  "chat.hint29": "What can I cook with tofu and greens?",
  "chat.hint30": "Help me use up leftover veggies before they spoil",
  "chat.refreshHints": "Shuffle",
  "chat.followUp": "You might also ask",
  "chat.placeholder": "Type a message...",
  "chat.trace": "Trace",
  "chat.ragRecall": "Relevant recall",
  "chat.ragRecallHint":
    "On: inject only memories relevant to this message (more focused)\nOff: inject the user’s full memory profile (more complete, may add noise)",
  "chat.copyCode": "Copy code",
  "chat.authErrorTitle": "API Key authentication failed",
  "chat.authErrorBody":
    "Your API key is invalid or not configured. Check backend/.env for settings.",
  "chat.authErrorLink": "Check backend status",
  "chat.errorPrefix": "Error",
  "chat.unknownError": "Unknown error",

  "trace.title": "Trace",
  "trace.collapse": "Collapse",
  "trace.expandAll": "Expand all",
  "trace.toolCalls": "{count} tool call",
  "trace.toolCallsPlural": "{count} tool calls",
  "trace.input": "Input",
  "trace.output": "Output",

  "memory.title": "User Food Profile",
  "memory.count": "{count} memories",
  "memory.export": "Export",
  "memory.exportTitle": "Export Markdown",
  "memory.loading": "Loading memories...",
  "memory.empty": "No memories yet",
  "memory.add": "Add memory",
  "memory.contentPlaceholder": "One keyword (e.g. lactose intolerant)",
  "memory.deleteConfirm": "Delete this memory entry?",
  "memory.viewSource": "View source session",
  "memory.revisionTitle": "Revision history",
  "memory.revisionCount": "{count} change(s)",
  "memory.revisionEmpty": "No revisions yet. Edits will appear here.",
  "memory.revisionContent": "Content",
  "memory.revisionCategory": "Category",
  "memory.revisionButton": "Revision history",
  "memory.original": "Original",
  "memory.fromSession": "From session",
  "memory.referenced": "Memories used",
  "memory.toastUpdated": "Memory updated",
  "memory.toastAdded": "{n} added",
  "memory.toastUpdatedCount": "{n} updated",
  "memory.toastCombined": "Memory updated: {parts}",

  "memory.source.judge": "From chat",
  "memory.source.manual": "Added manually",
  "memory.source.extract": "From chat",
  "memory.source.tool": "From chat",
  "memory.source.migrate": "From chat",
  "memory.source.chat": "From chat",
  "memory.source.unknown": "From chat",

  "memory.overview": "Overview",
  "memory.byCategory": "By category",
  "memory.bySource": "By source",
  "memory.total": "Total",
  "memory.categoryLabel": "Category",
  "memory.filterAll": "All sources",
  "memory.searchPlaceholder": "Search memories...",
  "memory.noMatch": "No matching memories",

  "category.Health & Dietary Restrictions": "Health & Dietary Restrictions",
  "category.Taste & Habits": "Taste & Habits",
  "category.Household & Context": "Household & Context",
  "category.Kitchen & Budget": "Kitchen & Budget",
  "category.Other": "Other",
  "category.Health & Dietary Restrictions.desc":
    "Allergies, diet limits, and long-term health-related eating constraints",
  "category.Taste & Habits.desc":
    "Preferred flavors, cooking styles, and everyday eating habits",
  "category.Household & Context.desc":
    "Household members and meal occasions such as weekday dinners or gatherings",
  "category.Kitchen & Budget.desc":
    "Cookware, appliances, grocery budget, and shopping constraints",
  "category.Other.desc":
    "Cooking-related notes that do not fit the categories above",
} as const;

type MessageKey = keyof typeof en;

/** Chinese copy */
const zh: Record<MessageKey, string> = {
  "common.confirm": "确认",
  "common.cancel": "取消",
  "common.close": "关闭",
  "common.delete": "删除",
  "common.edit": "编辑",
  "common.save": "保存",
  "common.saving": "保存中...",
  "common.rename": "重命名",
  "common.view": "查看",
  "common.online": "在线",
  "common.entries": "条",
  "common.entry": "条",
  "common.language": "语言",
  "common.lang.en": "English",
  "common.lang.zh": "中文",

  "login.subtitle": "登录你的 FoodMate 账号",
  "login.uid": "用户 ID",
  "login.uidPlaceholder": "请输入 uid",
  "login.password": "密码",
  "login.passwordPlaceholder": "请输入密码",
  "login.submit": "登录",
  "login.submitting": "登录中...",
  "login.error": "用户名或密码错误，请重试。",

  "nav.chat": "对话",
  "nav.memory": "记忆",
  "nav.memorySub": "系统",
  "nav.newChat": "新对话",
  "nav.recent": "最近",
  "nav.expand": "展开侧栏",
  "nav.collapse": "收起侧栏",
  "nav.signOut": "退出",
  "nav.deleteSession": "删除会话",
  "nav.deleteSessionMsg": "确定删除会话「{title}」？此操作不可撤销。",

  "chat.greeting": "你好，我是 FoodMate",
  "chat.intro": "你的家庭烹饪助手 — 试试",
  "chat.introHint": "今晚做什么菜？",
  "chat.hint1": "今晚做什么菜？",
  "chat.hint2": "推荐一道简单的家常菜",
  "chat.hint3": "我只有鸡蛋和番茄，能做什么？",
  "chat.hint4": "有什么适合孩子吃的菜？",
  "chat.hint5": "帮我规划一周晚餐",
  "chat.hint6": "减脂期间吃什么好？",
  "chat.hint7": "15 分钟能做好的快手菜",
  "chat.hint8": "冰箱只剩土豆和肉，怎么做？",
  "chat.hint9": "推荐一道下饭的硬菜",
  "chat.hint10": "适合夏天的清爽凉菜有哪些？",
  "chat.hint11": "想学一道不太失败的红烧肉",
  "chat.hint12": "素食者一周怎么搭配营养？",
  "chat.hint13": "有什么适合带便当的菜？",
  "chat.hint14": "感冒了吃什么比较养胃？",
  "chat.hint15": "用空气炸锅能做什么好吃的？",
  "chat.hint16": "推荐几道适合招待客人的菜",
  "chat.hint17": "我不太会切菜，有没有步骤少的菜？",
  "chat.hint18": "预算有限，一周菜谱怎么省钱？",
  "chat.hint19": "想吃辣，推荐一道川菜家常菜",
  "chat.hint20": "早餐除了粥和包子还能吃什么？",
  "chat.hint21": "怎么用剩米饭做出好吃的一餐？",
  "chat.hint22": "想做甜品，有没有零失败的配方？",
  "chat.hint23": "健身增肌期间晚餐吃什么？",
  "chat.hint24": "两个人吃，推荐一份刚好的双人菜单",
  "chat.hint25": "推荐一道好收拾的一锅出菜",
  "chat.hint26": "怎么做鱼才不腥？",
  "chat.hint27": "下雨天适合喝什么汤？",
  "chat.hint28": "家里有鸡胸肉，有健康做法吗？",
  "chat.hint29": "豆腐配青菜能做什么？",
  "chat.hint30": "剩菜快坏了，怎么尽快用掉？",
  "chat.refreshHints": "换一批",
  "chat.followUp": "你还可以问",
  "chat.placeholder": "输入消息...",
  "chat.trace": "调试追踪",
  "chat.ragRecall": "相关记忆召回",
  "chat.ragRecallHint":
    "开：只把与当前问题相关的记忆给 AI（更聚焦）\n关：把该用户的全部记忆都给 AI（更全面，可能有干扰）",
  "chat.copyCode": "复制代码",
  "chat.authErrorTitle": "API Key 认证失败",
  "chat.authErrorBody": "API Key 无效或未配置，请检查 backend/.env 设置。",
  "chat.authErrorLink": "查看后端状态",
  "chat.errorPrefix": "错误",
  "chat.unknownError": "未知错误",

  "trace.title": "调试追踪",
  "trace.collapse": "收起",
  "trace.expandAll": "全部展开",
  "trace.toolCalls": "{count} 次工具调用",
  "trace.toolCallsPlural": "{count} 次工具调用",
  "trace.input": "输入",
  "trace.output": "输出",

  "memory.title": "用户美食档案",
  "memory.count": "{count} 条记忆",
  "memory.export": "导出",
  "memory.exportTitle": "导出 Markdown",
  "memory.loading": "加载记忆中...",
  "memory.empty": "暂无记忆",
  "memory.add": "添加记忆",
  "memory.contentPlaceholder": "一个关键词（如：乳糖不耐受）",
  "memory.deleteConfirm": "确定删除这条记忆？",
  "memory.viewSource": "查看来源会话",
  "memory.revisionTitle": "修改记录",
  "memory.revisionCount": "共 {count} 次修改",
  "memory.revisionEmpty": "暂无修改记录，编辑后将显示在这里。",
  "memory.revisionContent": "内容",
  "memory.revisionCategory": "分类",
  "memory.revisionButton": "修改记录",
  "memory.original": "原话",
  "memory.fromSession": "来自会话",
  "memory.referenced": "本轮参考的记忆",
  "memory.toastUpdated": "记忆已更新",
  "memory.toastAdded": "新增 {n} 条",
  "memory.toastUpdatedCount": "更新 {n} 条",
  "memory.toastCombined": "记忆已更新：{parts}",

  "memory.source.judge": "来自对话",
  "memory.source.manual": "手动添加",
  "memory.source.extract": "来自对话",
  "memory.source.tool": "来自对话",
  "memory.source.migrate": "来自对话",
  "memory.source.chat": "来自对话",
  "memory.source.unknown": "来自对话",

  "memory.overview": "总览",
  "memory.byCategory": "按分类分布",
  "memory.bySource": "按来源分布",
  "memory.total": "总计",
  "memory.categoryLabel": "分类",
  "memory.filterAll": "全部来源",
  "memory.searchPlaceholder": "搜索记忆...",
  "memory.noMatch": "无匹配记忆",

  "category.Health & Dietary Restrictions": "健康与饮食限制",
  "category.Taste & Habits": "口味与习惯",
  "category.Household & Context": "家人与场景",
  "category.Kitchen & Budget": "厨房设备与预算",
  "category.Other": "其他",
  "category.Health & Dietary Restrictions.desc":
    "过敏、忌口、医生建议或需要长期遵守的饮食限制",
  "category.Taste & Habits.desc": "偏好口味、常见做法、吃饭节奏与习惯",
  "category.Household & Context.desc": "同住家人、聚餐或工作日等用餐场景",
  "category.Kitchen & Budget.desc": "锅具设备、食材预算与采购条件",
  "category.Other.desc": "暂不好归类、但仍与做饭相关的信息",
};

const dictionaries: Record<Locale, Record<MessageKey, string>> = { en, zh };

/**
 * The UI locale is currently fixed to English (the language switcher is hidden).
 *
 * @returns Locale
 */
export function detectLocale(): Locale {
  return "en";
}

/**
 * Read the stored locale (for non-React callers such as the store).
 *
 * @returns Locale
 */
export function getStoredLocale(): Locale {
  return detectLocale();
}

/**
 * Persist the locale preference and update document.lang.
 *
 * @param locale - Target locale
 */
export function persistLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // ignore
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }
}

/**
 * Look up copy by key, with optional {name} placeholders.
 *
 * @param locale - Locale
 * @param key - Message key
 * @param params - Optional placeholders
 * @returns Translated string
 */
export function translate(
  locale: Locale,
  key: MessageKey,
  params?: Record<string, string | number>,
): string {
  let text = dictionaries[locale][key] ?? dictionaries.en[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
    }
  }
  return text;
}

/**
 * Translate using the stored locale (for non-component callers).
 *
 * @param key - Message key
 * @param params - Optional placeholders
 * @returns Translated string
 */
export function tGlobal(
  key: MessageKey,
  params?: Record<string, string | number>,
): string {
  return translate(getStoredLocale(), key, params);
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Locale context provider wrapping the client tree that needs i18n.
 */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    persistLocale("en");
    setReady(true);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    persistLocale(next);
  }, []);

  const t = useCallback(
    (key: MessageKey, params?: Record<string, string | number>) =>
      translate(locale, key, params),
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  // Avoid SSR / first-paint locale flicker: still render before ready, using the detected locale
  if (!ready) {
    return (
      <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
    );
  }

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

/**
 * Read the current locale and translate function.
 *
 * @returns { locale, setLocale, t }
 */
export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return ctx;
}

/**
 * Shorthand: translate function only.
 *
 * @returns t function
 */
export function useT() {
  return useLocale().t;
}

export type { MessageKey };
