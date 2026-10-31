# Play24 — Integracja Home Assistant

Niestandardowa integracja Home Assistant dla serwisu Play24 (24.play.pl), umożliwiająca kompleksowe monitorowanie konta, podpiętych numerów (Multi-MSISDN), taryf, faktur, stanu konta na kartę, pakietów danych, aktywnych usług oraz cykli rozliczeniowych.

Wersja: **0.3.0**.

---

## Nowości w wersji 0.3.0

- **Dwa równorzędne sposoby logowania**:
  - **Metoda SMS OTP**: Podanie numeru telefonu i weryfikacja kodem SMS bezpośrednio w formularzu Home Assistant.
  - **Metoda JSESSIONID**: Ręczne wklejenie ciasteczka sesyjnego z przeglądarki.
  - Obie metody są w pełni obsługiwane podczas pierwszej konfiguracji, ponownego uwierzytelnienia (Re-auth) i rekonfiguracji (Reconfigure).
- **Rozbudowany model danych i encji**:
  - **Konto nadrzędne**: Liczba aktywnych numerów, zsynchronizowane numery, znacznik czasu aktualizacji, nieprzeczytane wiadomości oraz zbiorcza faktura konta (kwota, termin, status).
  - **Urządzenia podrzędne (per-MSISDN)**:
    - *Abonament (Postpaid)*: Kwota ostatniej faktury (PLN), termin płatności (data), status płatności, cykl rozliczeniowy, liczba dni pozostałych do końca cyklu (d), szczegóły oferty i numer główny grupy.
    - *Karta (Prepaid)*: Stan konta (PLN), data ważności połączeń wychodzących (data).
    - *Pakiety i usługi*: Wykrywanie limitu pakietu danych (GB) oraz licznik i lista aktywnych usług.
- **Bezpieczeństwo**: Całkowity zakaz logowania kodów SMS, ciasteczek, tokenów i haseł w dziennikach systemowych.

---

## Funkcje integracji

- **Obsługa wielu numerów (Multi-MSISDN)**: Automatyczne warstwowe wykrywanie wszystkich numerów telefonów przypisanych do konta Play24 oraz sekwencyjne przełączanie kontekstu (`accountContextChangeService.changeAccountContext`) zabezpieczone blokadą `asyncio.Lock()`.
- **Hierarchia urządzeń Home Assistant**:
  - **Konto Play24** (urządzenie nadrzędne / hub)
  - **Play24 `<MSISDN>`** (urządzenia podrzędne dla każdego numeru, powiązane przez `via_device_id`).
- **Odporność na błędy przejściowe**: Chwilowy błąd pobierania danych pojedynczego numeru nie powoduje utraty encji ani skasowania danych z pozostałych kart.
- **Rozpoznawanie typu oferty**: Automatyczna klasyfikacja taryf na `prepaid` (na kartę / odNOWA) oraz `postpaid` (abonament / biznes / grupy).
- **Zgodność ze standardami Home Assistant i HACS**:
  - Klasy urządzeń (`SensorDeviceClass.MONETARY`, `SensorDeviceClass.DATE`, `SensorDeviceClass.DATA_SIZE`, `SensorDeviceClass.TIMESTAMP`).
  - Klasy stanów (`SensorStateClass.MEASUREMENT`).
  - Jednostki zgodne z HA (`PLN`, `GB`, `d`).
  - Pełne tłumaczenia w języku polskim i angielskim (`pl.json`, `en.json`).
  - Kompletny zestaw testów jednostkowych (44 testy, 100% pass).

---

## Klasyfikacja dowodowa danych (Data Evidence Classification)

| Status | Pole / Encja | Identyfikator w HA | Klasa / Jednostka | Źródło w API Play24 |
|---|---|---|---|---|
| **CONFIRMED** | Liczba aktywnych numerów | `sensor.konto_play24_liczba_aktywnych_numerow` | — | `accountContextChangeService.getContextMsisdns` |
| **CONFIRMED** | Zsynchronizowane numery | `sensor.konto_play24_zsynchronizowane_numery` | Diagnostic, measurement | Coordinator `account_data` |
| **CONFIRMED** | Ostatnia aktualizacja | `sensor.konto_play24_ostatnia_aktualizacja` | Diagnostic, timestamp | Coordinator `last_update_success_time` |
| **CONFIRMED** | Nieprzeczytane wiadomości | `sensor.konto_play24_nieprzeczytane_wiadomosci` | Measurement | `messageRemoteService.getMessages` |
| **CONFIRMED** | Kwota faktury konta | `sensor.konto_play24_kwota_ostatniej_faktury_konta` | Monetary, `PLN` | `myAccountRemoteService.getFinanceTile` |
| **CONFIRMED** | Termin płatności faktury konta | `sensor.konto_play24_termin_platnosci_faktury_konta` | Date | `myAccountRemoteService.getFinanceTile` |
| **CONFIRMED** | Status płatności faktury konta | `sensor.konto_play24_status_platnosci_faktury_konta` | — | `myAccountRemoteService.getFinanceTile` |
| **CONFIRMED** | Taryfa | `sensor.play24_<msisdn>_taryfa` | — | `myAccountRemoteService.getOtherTile` (`tariff`) |
| **CONFIRMED** | Cykl rozliczeniowy | `sensor.play24_<msisdn>_cykl_rozliczeniowy` | — | `myAccountRemoteService.getOtherTile` (`billing_cycle`) |
| **CONFIRMED** | Pozostało dni cyklu | `sensor.play24_<msisdn>_pozostalo_dni_cyklu` | Measurement, `d` | `myAccountRemoteService.getOtherTile` (`remaining_cycle_days`) |
| **CONFIRMED** | Aktywne usługi | `sensor.play24_<msisdn>_aktywne_uslugi` | Measurement | `servicesRemoteService.getComponentsList` |
| **CONFIRMED** | Pakiet danych | `sensor.play24_<msisdn>_pakiet_danych` | Data size, `GB` | `servicesRemoteService.getComponentsList` (`data_package_gb`) |
| **CONFIRMED** | Kwota ostatniej faktury | `sensor.play24_<msisdn>_kwota_ostatniej_faktury` | Monetary, `PLN` | `myAccountRemoteService.getFinanceTile` (`invoice_amount_value`) |
| **CONFIRMED** | Termin płatności faktury | `sensor.play24_<msisdn>_termin_platnosci` | Date | `myAccountRemoteService.getFinanceTile` (`invoice_due_date`) |
| **CONFIRMED** | Status płatności | `sensor.play24_<msisdn>_status_platnosci` | — | `myAccountRemoteService.getFinanceTile` (`payment_status`) |
| **CONFIRMED** | Stan konta (prepaid) | `sensor.play24_<msisdn>_stan_konta` | Monetary, `PLN` | `myAccountRemoteService.getFinanceTile` (`account_balance`) |
| **CONFIRMED** | Ważność połączeń wychodzących | `sensor.play24_<msisdn>_waznosc_polaczen_wychodzacych` | Date | `myAccountRemoteService.getFinanceTile` (`outgoing_validity`) |

---

## Konfiguracja i Uwierzytelnianie

W Home Assistant przejdź do: **Ustawienia -> Urządzenia i usługi -> Dodaj integrację -> Play24**.

Wybierz preferowaną metodę logowania:

### Sposób 1 — Kod SMS (Zalecane)
1. Wybierz opcję **Numer telefonu i kod SMS**.
2. Podaj swój 9-cyfrowy numer telefonu zarejestrowany w Play24.
3. W kolejnym kroku wpisz kod weryfikacyjny SMS otrzymany na telefon.
4. Integracja automatycznie nawiąże i zapisze bezpieczną sesję.

### Sposób 2 — Ciasteczko JSESSIONID
1. Wybierz opcję **Ciasteczko JSESSIONID** lub wklej je bezpośrednio w formularzu początkowym.
2. Zaloguj się w przeglądarce do [24.play.pl](https://24.play.pl).
3. Otwórz narzędzia deweloperskie (F12 -> Storage / Application -> Cookies -> `24.play.pl`).
4. Skopiuj wartość ciasteczka `JSESSIONID` i zatwierdź formularz.

### Ponowne uwierzytelnienie (Re-auth) i Rekonfiguracja (Reconfigure)
Gdy sesja wygaśnie, kliknij **Konfiguruj ponownie** lub **Ponownie uwierzytelnij**. Dostępne są obie metody (SMS oraz JSESSIONID). Identyfikatory urządzeń, encji i historii encji w Home Assistant pozostają nienaruszone.

> [!WARNING]
> Ciasteczko `JSESSIONID` oraz kody SMS stanowią poufne dane uwierzytelniające. Nigdy nie udostępniaj ich osobom trzecim ani nie publikuj w publicznych logach.

---

## Uruchamianie testów

Testy jednostkowe działają w 100% offline w oparciu o syntetyczne mocki:

```bash
python3 -m pytest custom_components/play24/tests -v
```
