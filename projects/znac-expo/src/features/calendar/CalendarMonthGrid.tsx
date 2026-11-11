import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import {
  daysInMonth,
  formatIsoDate,
  isWeekendIso,
  parseIsoDate,
} from "../../domain/calendar";
import type { DayRecord, IsoDate, MonthRecord } from "../../domain/models";
import { getMobileTheme } from "../../theme";
import { Panel } from "../../ui";
import { regularDayBadgeKind } from "../day/dayVisualState";
import {
  CalendarDayCell,
  type CalendarDayCellModel,
  type CalendarDayVisualType,
} from "./CalendarDayCell";

const theme = getMobileTheme("dark");
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type CalendarMonthGridProps = {
  month: MonthRecord;
  today: IsoDate;
  onDayPress: (date: IsoDate) => void;
  onTodayLayout?: (y: number, height: number) => void;
};

export function CalendarMonthGrid({
  month,
  today,
  onDayPress,
  onTodayLayout,
}: CalendarMonthGridProps) {
  const cells = buildCalendarCells(month, today);
  const rows = chunkCells(cells);
  const [gridY, setGridY] = useState(0);
  const [rowFrames, setRowFrames] = useState<Record<number, { y: number; height: number }>>({});
  const todayRow = rowFrames[rows.findIndex((row) => row.some((cell) => cell.isToday && cell.inSelectedMonth))];
  useEffect(() => {
    if (todayRow) onTodayLayout?.(gridY + todayRow.y, todayRow.height);
  }, [gridY, today, todayRow, onTodayLayout]);

  return (
    <Panel style={styles.panel}>
      <View style={styles.weekdayRow}>
        {WEEKDAYS.map((weekday) => (
          <Text key={weekday} style={styles.weekday} numberOfLines={1} adjustsFontSizeToFit>
            {weekday}
          </Text>
        ))}
      </View>

      <View style={styles.grid} onLayout={(event) => setGridY(event.nativeEvent.layout.y)}>
        {rows.map((row, index) => (
          <View key={row[0]?.date} style={styles.dayRow} onLayout={(event) => {
            const { y, height } = event.nativeEvent.layout;
            setRowFrames((old) => old[index]?.y === y && old[index]?.height === height ? old : { ...old, [index]: { y, height } });
          }}>
            {row.map((cell) => (
              <CalendarDayCell
                key={cell.date}
                cell={cell}
                onPress={onDayPress}
              />
            ))}
          </View>
        ))}
      </View>
    </Panel>
  );
}

function buildCalendarCells(
  month: MonthRecord,
  today: IsoDate,
): CalendarDayCellModel[] {
  const firstDay = new Date(month.year, month.month - 1, 1);
  const leadingDays = mondayBasedWeekday(firstDay);
  const selectedMonthDays = daysInMonth(month.year, month.month);
  const visibleCellCount =
    Math.ceil((leadingDays + selectedMonthDays) / 7) * 7;
  const dayByDate = new Map(month.days.map((day) => [day.workDate, day]));

  return Array.from({ length: visibleCellCount }, (_, index) => {
    const date = new Date(month.year, month.month - 1, index - leadingDays + 1);
    const isoDate = formatIsoDate(date);
    const day = dayByDate.get(isoDate);
    const inSelectedMonth =
      date.getFullYear() === month.year && date.getMonth() === month.month - 1;

    return {
      date: isoDate,
      dayNumber: date.getDate(),
      inSelectedMonth,
      isToday: isoDate === today,
      isMaterialized: Boolean(day),
      visualType: classifyCalendarDay(isoDate, day),
    };
  });
}

function classifyCalendarDay(
  date: IsoDate,
  day?: DayRecord,
): CalendarDayVisualType {
  if (!day) {
    return isWeekendIso(date) ? "weekend" : "normal";
  }

  return regularDayBadgeKind(day) as CalendarDayVisualType;
}

function chunkCells(cells: CalendarDayCellModel[]): CalendarDayCellModel[][] {
  const rows: CalendarDayCellModel[][] = [];

  for (let index = 0; index < cells.length; index += 7) {
    rows.push(cells.slice(index, index + 7));
  }

  return rows;
}

function mondayBasedWeekday(date: Date): number {
  const parsed = parseIsoDate(formatIsoDate(date));

  if (!parsed) {
    return 0;
  }

  return (parsed.getDay() + 6) % 7;
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.sm,
  },
  weekdayRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  weekday: {
    flex: 1,
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: "700",
    textAlign: "center",
  },
  grid: {
    gap: theme.spacing.xs,
  },
  dayRow: {
    flexDirection: "row",
  },
});
