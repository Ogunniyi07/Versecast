import Image from "next/image";

export function Header() {
  return (
    <header className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2 sm:gap-2.5">
        <Image
          src="/logo.png"
          alt="Versecast"
          width={1424}
          height={344}
          priority
          className="h-7 w-auto min-[400px]:h-9 sm:h-11"
        />
        <span
          title="VerseCast is in early testing. Tell us when it gets a verse wrong."
          className="shrink-0 rounded-full border border-brand px-2 py-0.5 text-[10px] font-bold sm:text-[11px] uppercase tracking-wider text-brand"
        >
          Beta
        </span>
      </div>
      <span className="shrink-0 whitespace-nowrap rounded-full border border-navy px-3 py-1 text-xs sm:px-4 sm:py-1.5 sm:text-sm">KJV · English</span>
    </header>
  );
}
