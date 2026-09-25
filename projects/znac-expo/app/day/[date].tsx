import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo } from "react";
import { Pressable, Text, View } from "react-native";

import type { IsoDate, MonthRecord } from "../../src/domain/models";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";

export default function DayDetailsScreen() {
  const params = useLocalSearchParams<{ date?: string | string[] }>();
  const date = normalizeDateParam(params.date);

  const month = useMonthStore((state) => state.month);
  const loading = useMonthStore((state) => state.loading);
  const error = useMonthStore((state) => state.error);
  const loadMonth = useMonthStore((state) => state.load);
  const day = selectDayByIsoDate(month, date);
  const routeMonth = useMemo(() => (date ? isoYearMonth(date) : null), [date]);

  useEffect(() => {
    if (!routeMonth) {
      return;
    }

    if (monthMatchesDate(month, date)) {
      return;
    }

    loadMonth(routeMonth.year, routeMonth.month);
  }, [date, loadMonth, month, routeMonth]);

  if (!date || !routeMonth) {
    return (
      <View>
        <Text>Day details</Text>
        <Text>Invalid date</Text>
      </View>
    );
  }

  return (
    <View>
      <Text>Day details</Text>
      <Text>{date}</Text>
      {loading && <Text>Loading...</Text>}
      {error && <Text>{error}</Text>}
      <Text>{day ? "Day found" : "Day not found"}</Text>
      <Pressable
        onPress={() =>
          router.push({
            pathname: "/modals/day-editor",
            params: { date },
          })
        }
      >
        <Text>Edit day</Text>
      </Pressable>

      <Pressable
        onPress={() =>
          router.push({
            pathname: "/modals/break-editor",
            params: { date },
          })
        }
      >
        <Text>Edit break</Text>
      </Pressable>

      <Pressable
        onPress={() =>
          router.push({
            pathname: "/modals/delete-day",
            params: { date },
          })
        }
      >
        <Text>Delete day</Text>
      </Pressable>
    </View>
  );
}

function normalizeDateParam(value: string | string[] | undefined): IsoDate | "" {
  const date = Array.isArray(value) ? value[0] : value;

  if (!date || !isoYearMonth(date)) {
    return "";
  }

  return date;
}

function isoYearMonth(value: string): { year: number; month: number } | null {
  const match = /^(\d{4})-(\d{2})-\d{2}$/.exec(value);

  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);

  if (!Number.isInteger(year) || !Number.isInteger(month)) {
    return null;
  }

  if (month < 1 || month > 12) {
    return null;
  }

  return { year, month };
}

function monthMatchesDate(month: MonthRecord | null, date: IsoDate): boolean {
  const routeMonth = isoYearMonth(date);

  if (!month || !routeMonth) {
    return false;
  }

  return month.year === routeMonth.year && month.month === routeMonth.month;
}
