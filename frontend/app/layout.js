import "./globals.css";

export const metadata = {
  title: "AI Shopping Agent Demo | Autonomous Checkout",
  description: "Agentic commerce with human-in-the-loop authorization and live audit trail",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
