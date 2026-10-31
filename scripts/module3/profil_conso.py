from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
FICHIER = ROOT / "data/raw/courbes_de_charge/RES2-6-9.csv"

# Lecture complète (8,7 M de lignes) : compte environ une minute.
df = pd.read_csv(FICHIER, sep=";", dtype={"ID": str})

# Contrôles de base.
print("Lignes :", len(df))
print("Identifiants :", df["ID"].nunique())
print("Doublons (ID, horodate) :", df.duplicated(["ID", "horodate"]).sum())
print("Valeurs manquantes :", df["valeur"].isna().sum())
print(df["valeur"].describe().round(1))

# Les horodates ont un décalage (+01:00 / +02:00) : on convertit en heure française.
df["horodate"] = pd.to_datetime(df["horodate"], utc=True).dt.tz_convert("Europe/Paris")
df["heure"] = df["horodate"].dt.hour + df["horodate"].dt.minute / 60
df["mois"] = df["horodate"].dt.month

saisons = {"Été (juin-août)": [6, 7, 8], "Hiver (déc.-fév.)": [12, 1, 2]}

plt.figure(figsize=(10, 6))
for nom, mois in saisons.items():
    profil = df[df["mois"].isin(mois)].groupby("heure")["valeur"].mean()
    plt.plot(profil.index, profil.values, label=nom, linewidth=2)

plt.xlabel("Heure du jour (heure française)")
plt.ylabel("Valeur moyenne par client et par demi-heure (unité à confirmer)")
plt.title("Profil journalier de consommation résidentielle (RES2-6-9)")
plt.legend()
plt.grid(alpha=0.3)
plt.show()