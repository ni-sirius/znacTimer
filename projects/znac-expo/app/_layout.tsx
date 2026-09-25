import {
  DarkTheme,
  DefaultTheme,
  ThemeProvider,
} from "expo-router/react-navigation";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import "react-native-reanimated";

import { useColorScheme } from "@/hooks/use-color-scheme";
import { initializeDatabase } from "@/src/db";
import { useMonthStore } from "@/src/stores/monthStore";
import { useSettingsStore } from "@/src/stores/settingsStore";

export const unstable_settings = {
  anchor: "(tabs)",
};

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const loadMonth = useMonthStore((state) => state.load);
  const loadSettings = useSettingsStore((state) => state.load);
  const [databaseReady, setDatabaseReady] = useState(false);

  useEffect(() => {
    initializeDatabase().then(() => {
      setDatabaseReady(true);
    });
  }, []);

  useEffect(() => {
    if (!databaseReady) {
      return;
    }

    loadSettings();
    loadMonth();
  }, [databaseReady, loadSettings, loadMonth]);

  if (!databaseReady) {
    return null;
  }

  return (
    <ThemeProvider value={colorScheme === "dark" ? DarkTheme : DefaultTheme}>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />

        <Stack.Screen
          name="day/[date]"
          options={{
            title: "Day details",
          }}
        />

        <Stack.Screen
          name="modals/day-editor"
          options={{
            presentation: "modal",
            title: "Edit day",
          }}
        />

        <Stack.Screen
          name="modals/break-editor"
          options={{
            presentation: "modal",
            title: "Edit break",
          }}
        />

        <Stack.Screen
          name="modals/delete-day"
          options={{
            presentation: "modal",
            title: "Delete day",
          }}
        />

        <Stack.Screen
          name="modals/close-month"
          options={{
            presentation: "modal",
            title: "Close month",
          }}
        />

        <Stack.Screen
          name="modals/vacation-request"
          options={{
            presentation: "modal",
            title: "Request vacation",
          }}
        />
      </Stack>

      <StatusBar style="auto" />
    </ThemeProvider>
  );
}
