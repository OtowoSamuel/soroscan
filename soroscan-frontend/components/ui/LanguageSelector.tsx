"use client"

import * as React from "react"
import { useLocale, useTranslations } from "next-intl"
import { usePathname } from "next/navigation"
import { locales, defaultLocale, type AppLocale } from "@/lib/locales"
import { hardNavigate } from "@/lib/navigation"

const LOCALE_TRANSLATION_KEY: Record<AppLocale, "english" | "spanish"> = {
  en: "english",
  es: "spanish",
}

/** Strip any existing locale prefix and add the one for `nextLocale`. */
function localizePathname(pathname: string, nextLocale: AppLocale): string {
  const localePattern = new RegExp(`^/(${locales.join("|")})(?=/|$)`)
  const withoutLocale = pathname.replace(localePattern, "") || "/"

  if (nextLocale === defaultLocale) {
    return withoutLocale
  }
  return withoutLocale === "/" ? `/${nextLocale}` : `/${nextLocale}${withoutLocale}`
}

export function LanguageSelector() {
  const t = useTranslations("Language")
  const locale = useLocale() as AppLocale
  const pathname = usePathname()

  return (
    <div className="flex items-center gap-1.5">
      <label htmlFor="language-selector" className="sr-only">
        {t("switch")}
      </label>
      <select
        id="language-selector"
        value={locale}
        onChange={(event) => {
          const nextLocale = event.target.value as AppLocale
          document.cookie = `NEXT_LOCALE=${nextLocale};path=/;max-age=31536000;SameSite=Lax`
          hardNavigate(localizePathname(pathname, nextLocale))
        }}
        className="bg-transparent border border-terminal-gray/30 rounded-sm text-xs uppercase tracking-widest text-terminal-gray hover:text-terminal-green hover:border-terminal-green/30 transition-colors px-2 py-1 focus:outline-none focus:ring-1 focus:ring-terminal-green/50 font-terminal-mono"
      >
        {locales.map((value) => (
          <option key={value} value={value} className="bg-terminal-black text-terminal-gray">
            {t(LOCALE_TRANSLATION_KEY[value])}
          </option>
        ))}
      </select>
    </div>
  )
}
