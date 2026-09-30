export type MainTabName =
  | "index"
  | "calendar"
  | "statistics"
  | "vacation"
  | "settings";

export const MAIN_TABS = [
  {
    name: "index",
    title: "Overview",
    iosIcon: { default: "house", selected: "house.fill" },
    androidIcon: "home",
  },
  {
    name: "calendar",
    title: "Calendar",
    iosIcon: { default: "calendar", selected: "calendar" },
    androidIcon: "event",
  },
  {
    name: "statistics",
    title: "Statistics",
    iosIcon: { default: "chart.bar", selected: "chart.bar.fill" },
    androidIcon: "bar-chart",
  },
  {
    name: "vacation",
    title: "Vacation",
    iosIcon: { default: "sun.max", selected: "sun.max.fill" },
    androidIcon: "beach-access",
    future: true,
  },
  {
    name: "settings",
    title: "Settings",
    iosIcon: { default: "gearshape", selected: "gearshape.fill" },
    androidIcon: "settings",
  },
] as const satisfies readonly {
  name: MainTabName;
  title: string;
  iosIcon: {
    default: string;
    selected: string;
  };
  androidIcon: string;
  future?: boolean;
}[];
