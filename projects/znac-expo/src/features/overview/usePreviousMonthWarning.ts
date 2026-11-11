import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";

import { createRepository, getDatabase } from "../../db";
import type { IsoDate, MonthRecord } from "../../domain/models";
import { useMonthStore } from "../../stores/monthStore";
import { storeErrorMessage } from "../../stores/storeErrors";
import { previousMonthPeriod, shouldWarnAboutPreviousMonth } from "./previousMonthWarning";

export function usePreviousMonthWarning(year: number, month: number, today: IsoDate) {
  const changes = useMonthStore((state) => state.monthsByPeriod);
  const [previous, setPrevious] = useState<MonthRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    let active = true;
    setError(null);
    const [currentYear, currentMonth] = today.split("-").map(Number);
    if (year !== currentYear || month !== currentMonth) return;

    (async () => {
      try {
        const period = previousMonthPeriod(today);
        // A warning must not create or recalculate the previous month.
        const result = await createRepository(await getDatabase()).loadMonth(period.year, period.month);
        if (active && changes === useMonthStore.getState().monthsByPeriod) setPrevious(result);
      } catch (error) {
        if (active) setError(storeErrorMessage(error));
      }
    })();
    return () => { active = false; };
  }, [year, month, today, changes]));

  return { showWarning: shouldWarnAboutPreviousMonth(previous, year, month, today), error };
}
