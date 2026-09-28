import darkJson from "./source/dark.json";
import lightJson from "./source/light.json";

export type ThemeMode = "light" | "dark";

type ColorTree = {
  [key: string]: string | ColorTree;
};

type SourceTheme = {
  id: ThemeMode;
  colors: ColorTree;
};

export type MobileTheme = {
  mode: ThemeMode;
  source: SourceTheme;
  colors: {
    shell: string;
    surface: string;
    surfaceRaised: string;
    surfaceMuted: string;
    border: string;
    text: string;
    textMuted: string;
    textSubtle: string;
    primary: string;
    onPrimary: string;
    success: string;
    danger: string;
    dangerMuted: string;
    playerStop: string;
    playerDisabled: string;
    playerDisabledText: string;
    tabBar: string;
    tabBarBorder: string;
    regularDayPending: string;
    shadow: string;
  };
  row: {
    validDay: string;
    weekend: string;
    specialDay: string;
    missingTimes: string;
  };
  spacing: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
  radius: {
    sm: number;
    md: number;
    lg: number;
    pill: number;
  };
};

const SOURCES = {
  light: lightJson,
  dark: darkJson,
} as const;

export function getMobileTheme(mode: ThemeMode): MobileTheme {
  const source = resolveSourceTheme(mode);
  const mobilePrimary = mode === "dark" ? "#8b5cf6" : color(source, "primary");

  return {
    mode,
    source,
    colors: {
      shell: mode === "dark" ? "#10121d" : color(source, "shell.background"),
      surface: mode === "dark" ? "#171a29" : color(source, "tokens.panel_surface"),
      surfaceRaised:
        mode === "dark" ? "#1c2030" : color(source, "header.control"),
      surfaceMuted:
        mode === "dark" ? "#23243a" : color(source, "header.badge"),
      border: mode === "dark" ? "#2b3042" : color(source, "tokens.panel_border"),
      text: color(source, "tokens.panel_text"),
      textMuted: color(source, "tokens.panel_muted"),
      textSubtle: color(source, "palette.placeholder_text"),
      primary: mobilePrimary,
      onPrimary: mode === "dark" ? "#ffffff" : color(source, "on_primary"),
      success: color(source, "model.overtime_positive"),
      danger: color(source, "tokens.danger_text"),
      dangerMuted: color(source, "player.stop"),
      playerStop: color(source, "player.stop"),
      playerDisabled: color(source, "player.disabled"),
      playerDisabledText: color(source, "player.disabled_text"),
      tabBar: mode === "dark" ? "#10121d" : color(source, "menu.surface"),
      tabBarBorder: mode === "dark" ? "#2f3347" : color(source, "menu.border"),
      regularDayPending: mode === "dark" ? "#2b2147" : color(source, "header.badge"),
      shadow: toReactNativeColor(color(source, "table.shadow")),
    },
    row: {
      validDay: color(source, "row.valid_day"),
      weekend: color(source, "row.weekend"),
      specialDay: color(source, "row.special_day"),
      missingTimes: color(source, "row.missing_times"),
    },
    spacing: {
      xs: 4,
      sm: 8,
      md: 12,
      lg: 16,
      xl: 24,
    },
    radius: {
      sm: 4,
      md: 6,
      lg: 8,
      pill: 999,
    },
  };
}

export function resolveSourceTheme(mode: ThemeMode): SourceTheme {
  const source = SOURCES[mode];

  return {
    id: source.id as ThemeMode,
    colors: resolveColorTree(source.colors),
  };
}

export function color(theme: SourceTheme, path: string): string {
  const value = valueAtPath(theme.colors, path);

  if (typeof value !== "string") {
    throw new Error(`Theme path "${path}" is a group, not a color.`);
  }

  return value;
}

export function toReactNativeColor(value: string): string {
  if (/^#[0-9a-fA-F]{8}$/.test(value)) {
    const alpha = value.slice(1, 3);
    const red = value.slice(3, 5);
    const green = value.slice(5, 7);
    const blue = value.slice(7, 9);

    return `#${red}${green}${blue}${alpha}`.toLowerCase();
  }

  return value.toLowerCase();
}

function resolveColorTree(colors: ColorTree): ColorTree {
  const resolved: ColorTree = {};

  function resolveValue(path: string): string {
    const value = valueAtPath(colors, path);

    if (typeof value !== "string") {
      throw new Error(`Theme reference "${path}" points to a group.`);
    }

    if (!value.startsWith("@")) {
      return value.toLowerCase();
    }

    return resolveValue(value.slice(1));
  }

  function walk(source: ColorTree, target: ColorTree, prefix = "") {
    for (const [key, value] of Object.entries(source)) {
      const path = prefix ? `${prefix}.${key}` : key;

      if (typeof value === "string") {
        target[key] = resolveValue(path);
      } else {
        const child: ColorTree = {};
        target[key] = child;
        walk(value, child, path);
      }
    }
  }

  walk(colors, resolved);

  return resolved;
}

function valueAtPath(colors: ColorTree, path: string): string | ColorTree {
  let current: string | ColorTree = colors;

  for (const part of path.split(".")) {
    if (typeof current === "string" || !(part in current)) {
      throw new Error(`Theme path "${path}" does not exist.`);
    }

    current = current[part];
  }

  return current;
}
