import type { Metadata } from "next";
import { Montserrat, Source_Serif_4 } from "next/font/google";
import Script from "next/script";
import "./globals.css";

const sans = Montserrat({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const serif = Source_Serif_4({ subsets: ["latin"], variable: "--font-serif", display: "swap" });

export const metadata: Metadata = {
  title: "VerseCast",
  description: "Say a Bible reference and the KJV verse appears on screen.",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32" },
      { url: "/icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body className="font-sans">
        {children}
        {/* Visitor counts: https://versecast.goatcounter.com (no cookies) */}
        <Script data-goatcounter="https://versecast.goatcounter.com/count" src="https://gc.zgo.at/count.js" strategy="afterInteractive" />
      </body>
    </html>
  );
}
