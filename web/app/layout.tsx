// Base minimale pour développer l'interface (membre 4).
// À remplacer par le squelette du membre 5 lors de la fusion si besoin.
import type { ReactNode } from "react";

export const metadata = { title: "Pilote" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
