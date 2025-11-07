# ui/pages/evenements.py
"""
Page de gestion des événements spéciaux impactant la planification
"""
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Optional

from models.event import Event, EventManager


def render_evenements_page():
    """Affiche la page de gestion des événements"""
    st.title("📅 Événements Spéciaux")
    st.markdown(
        "Gérez les événements qui impactent votre planification (Davos, salons, jours fériés, etc.). "
        "Ces événements influencent les suggestions de l'Assistant Besoin Jour."
    )

    # Avertissement important
    st.info(
        "💡 **Important :** Après avoir ajouté/modifié des événements, "
        "vous devez **régénérer le budget** (page 'Budget Annuel' → bouton '🔄 Générer Budget') "
        "pour que les événements soient pris en compte par l'Assistant Besoin Jour.",
        icon="⚠️"
    )

    # Vérifier qu'un budget est généré
    bs = st.session_state.get('budget_state', {})
    if not bs or 'year' not in bs:
        st.warning(
            "⚠️ Aucun budget annuel en mémoire. "
            "Générez d'abord un budget via la page **Budget Annuel** pour gérer les événements."
        )
        st.stop()

    year = bs['year']

    # Charger les événements
    events = EventManager.get_events_for_year(year)

    # === Section 1: Actions rapides ===
    with st.container(border=True):
        st.subheader("⚡ Actions Rapides")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("➕ Nouvel Événement", use_container_width=True, type="primary"):
                st.session_state.show_event_form = True
                st.session_state.edit_event_date = None

        with col2:
            if st.button("📋 Charger Événements Types", use_container_width=True):
                EventManager.create_default_events(year)
                st.success(f"✅ Événements types ajoutés pour {year}")
                st.rerun()

        with col3:
            if st.button("🗑️ Effacer Tous", use_container_width=True):
                if events:
                    st.session_state.confirm_delete_all = True
                else:
                    st.info("Aucun événement à effacer")

        # Confirmation suppression globale
        if st.session_state.get('confirm_delete_all', False):
            st.warning(f"⚠️ Confirmer la suppression de **{len(events)} événement(s)** ?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Oui, effacer tout", type="primary"):
                    st.session_state.calendar_events = {}
                    st.session_state.confirm_delete_all = False
                    st.success("✅ Tous les événements ont été supprimés")
                    st.rerun()
            with col_no:
                if st.button("Annuler"):
                    st.session_state.confirm_delete_all = False
                    st.rerun()

    # === Section 2: Statistiques ===
    if events:
        with st.container(border=True):
            st.subheader("📊 Statistiques")
            col1, col2, col3, col4 = st.columns(4)

            # Compter par type
            type_counts = {'critical': 0, 'major': 0, 'minor': 0}
            for evt in events.values():
                type_counts[evt.event_type] += 1

            with col1:
                st.metric("Total Événements", len(events))
            with col2:
                st.metric("🔴 Critiques", type_counts['critical'])
            with col3:
                st.metric("🟠 Majeurs", type_counts['major'])
            with col4:
                st.metric("🟡 Mineurs", type_counts['minor'])

    # === Section 3: Formulaire d'ajout/édition ===
    if st.session_state.get('show_event_form', False):
        with st.container(border=True):
            st.subheader("📝 Formulaire Événement")

            # Édition ou nouveau ?
            edit_date = st.session_state.get('edit_event_date')
            existing_event = EventManager.get_event(edit_date) if edit_date else None

            # Déterminer la valeur par défaut pour la date
            # S'assurer qu'elle est dans l'intervalle [year-01-01, year-12-31]
            if existing_event:
                default_date = existing_event.date
            else:
                today = date.today()
                if today.year == year:
                    default_date = today
                else:
                    # Si on est dans une année différente, prendre le 1er janvier de l'année du budget
                    default_date = date(year, 1, 1)

            col_form1, col_form2 = st.columns(2)

            with col_form1:
                event_date = st.date_input(
                    "Date de l'événement",
                    value=default_date,
                    min_value=date(year, 1, 1),
                    max_value=date(year, 12, 31),
                    key="event_form_date"
                )

                event_name = st.text_input(
                    "Nom de l'événement",
                    value=existing_event.name if existing_event else "",
                    placeholder="Ex: Davos - Jour 1",
                    key="event_form_name"
                )

                event_type = st.selectbox(
                    "Type d'événement",
                    options=['minor', 'major', 'critical'],
                    format_func=lambda x: {
                        'minor': '🟡 Mineur (impact léger)',
                        'major': '🟠 Majeur (impact fort)',
                        'critical': '🔴 Critique (bloquer complètement)'
                    }[x],
                    index=['minor', 'major', 'critical'].index(
                        existing_event.event_type if existing_event else 'minor'
                    ),
                    key="event_form_type"
                )

            with col_form2:
                event_description = st.text_area(
                    "Description (optionnelle)",
                    value=existing_event.description if existing_event else "",
                    placeholder="Décrivez l'impact sur les opérations...",
                    height=100,
                    key="event_form_desc"
                )

                penalty_factor = st.slider(
                    "Facteur de pénalité",
                    min_value=0.0,
                    max_value=1.0,
                    value=existing_event.penalty_factor if existing_event else Event._default_penalty_for_type(event_type),
                    step=0.1,
                    help="0.0 = pas d'impact, 1.0 = bloquer complètement cette journée",
                    key="event_form_penalty"
                )

                st.caption(f"**Pénalité suggérée pour '{event_type}':** {Event._default_penalty_for_type(event_type)}")

            # Boutons d'action
            col_save, col_cancel = st.columns(2)

            with col_save:
                if st.button("💾 Enregistrer", type="primary", use_container_width=True):
                    if not event_name.strip():
                        st.error("⚠️ Le nom de l'événement est obligatoire")
                    else:
                        new_event = Event(
                            date=event_date,
                            name=event_name.strip(),
                            event_type=event_type,
                            description=event_description.strip(),
                            penalty_factor=penalty_factor
                        )
                        EventManager.add_event(new_event)
                        st.success(f"✅ Événement '{event_name}' enregistré pour le {event_date}")
                        st.session_state.show_event_form = False
                        st.session_state.edit_event_date = None
                        st.rerun()

            with col_cancel:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state.show_event_form = False
                    st.session_state.edit_event_date = None
                    st.rerun()

    # === Section 4: Liste des événements ===
    with st.container(border=True):
        st.subheader(f"📋 Événements {year}")

        if not events:
            st.info(
                "Aucun événement défini pour cette année. "
                "Cliquez sur '➕ Nouvel Événement' ou 'Charger Événements Types'."
            )
        else:
            # Préparer le DataFrame pour affichage
            events_data = []
            for evt in sorted(events.values(), key=lambda e: e.date):
                events_data.append({
                    'Date': evt.date,
                    'Type': evt.get_label_fr(),
                    'Nom': evt.name,
                    'Pénalité': f"{evt.penalty_factor:.1f}",
                    'Description': evt.description[:50] + '...' if len(evt.description) > 50 else evt.description,
                    '_date_obj': evt.date,  # Pour les actions
                    '_color': evt.get_color()
                })

            events_df = pd.DataFrame(events_data)

            # Afficher sous forme de tableau stylisé
            for idx, row in events_df.iterrows():
                with st.container():
                    col_info, col_actions = st.columns([5, 1])

                    with col_info:
                        st.markdown(
                            f"""
                            <div style="
                                border-left: 4px solid {row['_color']};
                                padding: 12px 16px;
                                margin: 8px 0;
                                background: #f8f9fa;
                                border-radius: 4px;
                            ">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <strong style="font-size: 1.1em;">{row['Nom']}</strong>
                                        <span style="margin-left: 12px; color: #666;">
                                            {row['Date'].strftime('%d/%m/%Y')} • {row['Type']} • Pénalité: {row['Pénalité']}
                                        </span>
                                    </div>
                                </div>
                                {f"<div style='margin-top: 6px; color: #555; font-size: 0.9em;'>{row['Description']}</div>" if row['Description'] else ""}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                    with col_actions:
                        col_edit, col_del = st.columns(2)
                        with col_edit:
                            if st.button("✏️", key=f"edit_{idx}", help="Modifier"):
                                st.session_state.show_event_form = True
                                st.session_state.edit_event_date = row['_date_obj']
                                st.rerun()
                        with col_del:
                            if st.button("🗑️", key=f"del_{idx}", help="Supprimer"):
                                EventManager.remove_event(row['_date_obj'])
                                st.success(f"✅ Événement du {row['_date_obj']} supprimé")
                                st.rerun()

    # === Section 5: Visualisation calendrier ===
    if events:
        with st.expander("📅 Visualisation Calendrier", expanded=False):
            st.markdown("**Vue mensuelle des événements**")

            # Créer un calendrier visuel simple
            months = sorted(set(evt.date.month for evt in events.values()))

            for month in months:
                month_events = [evt for evt in events.values() if evt.date.month == month]
                if month_events:
                    month_name = datetime(year, month, 1).strftime('%B %Y')
                    st.markdown(f"### {month_name}")

                    cols = st.columns(7)
                    for i, evt in enumerate(sorted(month_events, key=lambda e: e.date)):
                        with cols[i % 7]:
                            st.markdown(
                                f"""
                                <div style="
                                    background: {evt.get_color()}22;
                                    border: 2px solid {evt.get_color()};
                                    border-radius: 8px;
                                    padding: 8px;
                                    text-align: center;
                                    margin: 4px 0;
                                ">
                                    <div style="font-weight: bold; font-size: 1.2em;">
                                        {evt.date.day}
                                    </div>
                                    <div style="font-size: 0.8em;">
                                        {evt.name[:15]}...
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

    # === Section 6: Import/Export ===
    with st.expander("📤 Import / Export", expanded=False):
        col_imp, col_exp = st.columns(2)

        with col_imp:
            st.markdown("**Import depuis JSON**")
            uploaded_file = st.file_uploader(
                "Charger un fichier JSON d'événements",
                type=['json'],
                key="import_events_json"
            )
            if uploaded_file:
                if st.button("📥 Importer", key="btn_import"):
                    try:
                        import json
                        import tempfile

                        # Sauvegarder temporairement
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                            tmp.write(uploaded_file.getvalue().decode('utf-8'))
                            tmp_path = tmp.name

                        EventManager.import_from_json(tmp_path)
                        st.success("✅ Événements importés avec succès")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erreur lors de l'import: {e}")

        with col_exp:
            st.markdown("**Export vers JSON**")
            if events:
                if st.button("📤 Exporter", key="btn_export"):
                    import json
                    import tempfile

                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                        EventManager.export_to_json(tmp.name, year)
                        tmp_path = tmp.name

                    with open(tmp_path, 'r') as f:
                        json_data = f.read()

                    st.download_button(
                        label="⬇️ Télécharger JSON",
                        data=json_data,
                        file_name=f"evenements_{year}.json",
                        mime="application/json"
                    )
            else:
                st.info("Aucun événement à exporter")

    # === Section 7: Aide ===
    with st.expander("💡 Aide - Types d'événements", expanded=False):
        st.markdown("""
        ### Types d'événements et leurs impacts

        #### 🔴 **Critique** (Pénalité: 1.0)
        **Usage:** Situations exceptionnelles où aucune modification ne doit être faite
        - Grèves majeures
        - Fermetures de terminaux
        - Situations d'urgence
        - **Impact:** L'assistant **évitera complètement** ces jours pour tout ajustement

        #### 🟠 **Majeur** (Pénalité: 0.8)
        **Usage:** Événements importants avec forte affluence attendue
        - Davos (Forum économique)
        - Salons internationaux (Auto, Horlogerie)
        - Grands événements sportifs
        - **Impact:** L'assistant **fortement dissuadé** de retirer des ressources ces jours-là

        #### 🟡 **Mineur** (Pénalité: 0.3)
        **Usage:** Événements locaux ou jours avec comportement légèrement atypique
        - Jours fériés locaux
        - Fêtes de Genève
        - Petits événements
        - **Impact:** L'assistant fera preuve de **prudence** mais pourra ajuster si nécessaire

        ### Comment l'assistant utilise ces informations

        #### 🚫 **Filtre de blocage (pénalité >= 0.7)**
        Les événements **Critiques (1.0)** et **Majeurs (0.8)** sont **complètement bloqués**.
        - Les slots de ces journées sont **exclus AVANT le scoring**
        - Aucune suggestion ne sera générée pour ces dates
        - ✅ Protection absolue garantie

        #### 📊 **Pénalité dans le score (pénalité < 0.7)**
        Les événements **Mineurs (0.3)** réduisent le score mais ne bloquent pas :
        - La pénalité compte pour **10% du score final**
        - **Exemple :** Score 0.75 → avec mineur 0.3 → 0.75 - (0.10 × 0.3) = **0.72**
        - L'assistant fait preuve de **prudence** mais garde la flexibilité

        #### 💡 **En résumé**
        - **Critique/Majeur :** Blocage total (aucune suggestion générée)
        - **Mineur :** Réduction du score (suggestions possibles mais moins prioritaires)

        ⚠️ **N'oubliez pas** de régénérer le budget après avoir modifié les événements !
        """)


# Initialisation session_state
if 'show_event_form' not in st.session_state:
    st.session_state.show_event_form = False
if 'edit_event_date' not in st.session_state:
    st.session_state.edit_event_date = None
if 'confirm_delete_all' not in st.session_state:
    st.session_state.confirm_delete_all = False
