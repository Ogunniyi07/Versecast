import Image from "next/image";

export function Header() {
  return (
    <header className="flex items-center justify-between gap-4">
      <Image
        src="/logo.png"
        alt="Versecast"
        width={1424}
        height={344}
        priority
        className="h-9 w-auto sm:h-11"
      />
      <span className="rounded-full border border-navy px-4 py-1.5 text-sm whitespace-nowrap">KJV · English</span>
    </header>
  );
}
