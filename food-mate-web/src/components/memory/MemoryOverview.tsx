"use client";

import {
  MEMORY_CATEGORIES,
  type MemoryCategory,
  type MemoryEntry,
} from "@/lib/types";
import {
  USER_SOURCE_GROUPS,
  getCategoryVisual,
  getSourceVisual,
  toUserSourceGroup,
  type UserSourceGroup,
} from "@/lib/memoryVisuals";
import { useT, type MessageKey } from "@/lib/i18n";

interface Props {
  entries: MemoryEntry[];
}

interface CategoryStat {
  category: MemoryCategory;
  count: number;
  pct: number;
}

const DONUT_SIZE = 156;
const DONUT_STROKE = 26;
const DONUT_GAP = 5;

/**
 * 记忆总览：左侧分类列表 + 右侧环形图 + 来源标签。
 */
export default function MemoryOverview({ entries }: Props) {
  const t = useT();
  const total = entries.length;

  const byCategory: CategoryStat[] = MEMORY_CATEGORIES.map((cat) => {
    const count = entries.filter((e) => e.category === cat).length;
    return {
      category: cat,
      count,
      pct: total > 0 ? Math.round((count / total) * 100) : 0,
    };
  });

  const bySource = USER_SOURCE_GROUPS.map((group) => ({
    source: group,
    count: entries.filter((e) => toUserSourceGroup(e.source_type) === group)
      .length,
  })).filter((item) => item.count > 0);

  return (
    <div
      className="rounded-xl p-4 space-y-4"
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
      }}
    >
      <h2
        className="text-[13px] font-semibold"
        style={{ color: "var(--text-primary)" }}
      >
        {t("memory.overview")}
      </h2>

      {/* 按分类分布：左列表 + 右环 */}
      <div>
        <p
          className="text-[11px] font-medium mb-3"
          style={{ color: "var(--text-muted)" }}
        >
          {t("memory.byCategory")}
        </p>
        <div className="flex items-center gap-6 flex-wrap">
          <CategoryBars stats={byCategory} />
          <CategoryDonut stats={byCategory} total={total} />
        </div>
      </div>

      {/* 按来源分布（用户可见两类） */}
      {bySource.length > 0 && (
        <div>
          <p
            className="text-[11px] font-medium mb-2"
            style={{ color: "var(--text-muted)" }}
          >
            {t("memory.bySource")}
          </p>
          <div className="flex flex-wrap gap-2">
            {bySource.map(({ source, count }) => (
              <SourceChip key={source} source={source} count={count} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * 分类分布条：图标、名称、进度条与数量。
 *
 * 参数:
 *   stats - 各分类计数与百分比
 */
function CategoryBars({ stats }: { stats: CategoryStat[] }) {
  const t = useT();
  return (
    <div className="space-y-2 flex-1 min-w-[220px]">
      {stats.map(({ category, count, pct }) => {
        const visual = getCategoryVisual(category);
        const Icon = visual.icon;
        return (
          <div key={category} className="flex items-center gap-2">
            <div
              className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
              style={{ background: visual.bg }}
            >
              <Icon className="w-3.5 h-3.5" style={{ color: visual.color }} />
            </div>
            <span
              className="text-[12px] w-28 truncate shrink-0"
              style={{ color: "var(--text-secondary)" }}
              title={t(`category.${category}` as MessageKey)}
            >
              {t(`category.${category}` as MessageKey)}
            </span>
            <div
              className="flex-1 h-1.5 rounded-full overflow-hidden"
              style={{ background: "var(--border)" }}
            >
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${pct}%`,
                  background: visual.color,
                  minWidth: count > 0 ? 4 : 0,
                }}
              />
            </div>
            <span
              className="text-[11px] font-mono w-6 text-right shrink-0"
              style={{ color: "var(--text-muted)" }}
            >
              {count}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * 分类占比环形图，中心显示条目总数，环上标注百分比。
 *
 * 参数:
 *   stats - 各分类计数与百分比
 *   total - 记忆条目总数
 */
function CategoryDonut({
  stats,
  total,
}: {
  stats: CategoryStat[];
  total: number;
}) {
  const t = useT();
  const radius = (DONUT_SIZE - DONUT_STROKE) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = DONUT_SIZE / 2;

  const active = stats.filter((s) => s.count > 0);
  const gapTotal = active.length > 1 ? DONUT_GAP * active.length : 0;
  const usable = Math.max(circumference - gapTotal, 0);

  let cursor = 0;
  const arcs =
    total === 0
      ? []
      : active.map((item) => {
          const length = (item.count / total) * usable;
          const mid = cursor + length / 2;
          // 从 12 点顺时针；SVG 角度从 3 点起算
          const angle = -Math.PI / 2 + (mid / circumference) * 2 * Math.PI;
          const dashoffset = circumference / 4 - cursor;
          cursor += length + (active.length > 1 ? DONUT_GAP : 0);
          return {
            category: item.category,
            pct: item.pct,
            length,
            dashoffset,
            color: getCategoryVisual(item.category).color,
            labelX: center + radius * Math.cos(angle),
            labelY: center + radius * Math.sin(angle),
          };
        });

  return (
    <div
      className="relative shrink-0 ml-auto"
      style={{ width: DONUT_SIZE, height: DONUT_SIZE }}
    >
      <svg
        width={DONUT_SIZE}
        height={DONUT_SIZE}
        viewBox={`0 0 ${DONUT_SIZE} ${DONUT_SIZE}`}
        className="block"
        aria-hidden
      >
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth={DONUT_STROKE}
        />
        {arcs.map((arc) => (
          <circle
            key={arc.category}
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={arc.color}
            strokeWidth={DONUT_STROKE}
            strokeLinecap="butt"
            strokeDasharray={`${arc.length} ${circumference - arc.length}`}
            strokeDashoffset={arc.dashoffset}
          />
        ))}
        {arcs
          .filter((arc) => arc.pct >= 8)
          .map((arc) => (
            <text
              key={`${arc.category}-pct`}
              x={arc.labelX}
              y={arc.labelY}
              textAnchor="middle"
              dominantBaseline="central"
              fill="#fff"
              fontSize="9.5"
              fontWeight="600"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {arc.pct}%
            </text>
          ))}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span
          className="text-[22px] font-bold leading-none tabular-nums"
          style={{ color: "var(--text-primary)" }}
        >
          {total}
        </span>
        <span className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
          {t("memory.total")}
        </span>
      </div>
    </div>
  );
}

/**
 * 来源数量小标签。
 *
 * 参数:
 *   source - 用户可见来源分组
 *   count - 该来源条目数
 */
function SourceChip({
  source,
  count,
}: {
  source: UserSourceGroup;
  count: number;
}) {
  const t = useT();
  const visual = getSourceVisual(source);
  const Icon = visual.icon;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11px]"
      style={{
        background: visual.bg,
        color: visual.color,
        border: `1px solid ${visual.color}33`,
      }}
    >
      <Icon className="w-3 h-3" />
      {t(visual.labelKey)}
      <span className="font-mono font-semibold">{count}</span>
    </span>
  );
}
