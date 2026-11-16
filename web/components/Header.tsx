import Image from "next/image";

export function Header() {
  return (
    <header className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-2.5">
        <Image
          src="/logo.png"
          alt="Versecast"
          width={1424}
          height={344}
          priority
          className="h-9 w-auto sm:h-11"
        />
        <span
          title="VerseCast is in early testing. Tell us when it gets a verse wrong."
          className="rounded-full border border-brand px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-brand"
        >
          Beta
        </span>
      </div>
      <span className="rounded-full border border-navy px-4 py-1.5 text-sm whitespace-nowrap">KJV · English</span>
    </header>
  );
}
