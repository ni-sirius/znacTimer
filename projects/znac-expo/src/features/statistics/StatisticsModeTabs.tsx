import { SegmentedControl } from "../../ui";

export type StatisticsMode = "month" | "year" | "all";

type StatisticsModeTabsProps = {
  value: StatisticsMode;
  onChange: (value: StatisticsMode) => void;
};

const OPTIONS: { label: string; value: StatisticsMode }[] = [
  { label: "Month", value: "month" },
  { label: "Year", value: "year" },
  { label: "All time", value: "all" },
];

export function StatisticsModeTabs({
  value,
  onChange,
}: StatisticsModeTabsProps) {
  return <SegmentedControl value={value} options={OPTIONS} onChange={onChange} />;
}
