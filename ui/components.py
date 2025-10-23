"""
Composants UI réutilisables
"""
import streamlit as st
import pandas as pd
from config.constants import TIME_SLOTS, JOURS_FR, SAISONS_ORDRE
from core.planning import _ensure_grid, _apply_bulk_range
from utils.helpers import canon


@st.dialog("Mode d'emploi")
def show_help_dialog():
    """Affiche la boîte de dialogue d'aide"""
    st.caption("Guide d'utilisation du Planificateur Budgétaire OPT – Genève Aéroport")

    # Objectif de l'outil
    with st.container():
        st.markdown(
            """
            <div class="objectif-container">
                <h3>Objectif de l'outil</h3>
                <div><b>✔ Construire</b> des grilles jour-type par catégorie pour estimer les heures et les coûts.</div>
                <div><b>✔ Générer</b> un Budget Annuel consolidé à partir de ces grilles et du calendrier des saisons.</div>
                <div><b>✔ Appliquer</b> des règles ponctuelles dans <i>Besoin Jour</i> pour ajuster certains jours/plages <b>sans modifier</b> les jours-types de base.</div>
                <div><b>✔ Exporter/Importer</b> un scénario complet pour le sauvegarder, le partager ou le reprendre plus tard.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Pré-requis
    with st.container(border=True):
        st.markdown("### Pré-requis")
        st.markdown(
            """
            1. Démarrer en choisissant la **base 2026** (ou en chargeant un scénario `.xlsx` existant).
            2. S'assurer que les **périmètres** par catégorie sont correctement définis.
            3. Vérifier que les **tarifs horaires** du personnel sont à jour dans la page *Configuration*.
            """
        )

    # Parcours Recommandé
    st.markdown("### Parcours Recommandé")
    st.markdown(
        """
        <div class="parcours-grid">
          <div class="parcours-card"><h4>1. Configuration</h4><p>Vérifiez les tarifs, saisons de référence et périmètres.</p></div>
          <div class="parcours-card"><h4>2. Planification</h4><p>Éditez ou créez les grilles pour chaque jour-type.</p></div>
          <div class="parcours-card"><h4>3. Budget Annuel</h4><p>Générez la projection annuelle et analysez les coûts.</p></div>
          <div class="parcours-card"><h4>4. Besoin Jour</h4><p>Appliquez des ajustements ponctuels si nécessaire.</p></div>
          <div class="parcours-card"><h4>5. Export</h4><p>Sauvegardez votre scénario via la barre latérale.</p></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    # Concepts Importants
    with st.container(border=True):
        st.markdown("### Concepts Importants")
        st.markdown(
            """
            - **Jour-type (JT)** : Modèle de planification (`Jour + Saison`). Grille binaire (0/1).
            - **Périmètre** : Poste ou zone opérationnelle (ex: *Check in 1*).
            - **Catégorie** : Regroupement de périmètres (AT, CSC, etc.).
            - **Règle *Besoin Jour*** : Modification **temporaire** (dates spécifiques), n'altère pas les JTs.
            - **Autosave** : Les règles *Besoin Jour* sont dans `rules_besoin_jour.json`.
            """
        )

    # Checklist
    st.success("✅ Checklist Rapide")
    st.markdown(
        "- [ ] **Configuration** : Tarifs et périmètres OK.\n"
        "- [ ] **Planification** : Jours-types nécessaires OK.\n"
        "- [ ] **Budget Annuel** : Mapping coûts OK & Budget généré.\n"
        "- [ ] **Besoin Jour** : Ajustements ponctuels OK (si besoin).\n"
        "- [ ] **Export** : Scénario sauvegardé."
    )

    col1, col2, col3 = st.columns([0.5, 0.3, 0.3])
    with col2:
        if st.button("Fermer", type="primary", use_container_width=False):
            st.session_state.show_help_dialog = False
            st.rerun()


def _render_grid_for_edit(category_key: str, jt_key_requested: str, title_suffix: str = ""):
    """Affiche une grille de planification éditable"""
    perimetres = st.session_state.perimetres.get(category_key, [])
    if not perimetres:
        st.warning(f"Aucun périmètre défini pour '{category_key}'.")
        return

    planning_dict = st.session_state.planning_data.setdefault(category_key, {})
    time_slots = TIME_SLOTS

    stored_key, grid_src = _ensure_grid(planning_dict, jt_key_requested, perimetres, time_slots)

    st.subheader(f"Grille {category_key} — {stored_key} {title_suffix}")

    if grid_src.index.name is None:
        grid_src.index.name = "Perimetre"

    grid_to_edit = grid_src.reset_index().copy()

    # Clé unique pour éviter les collisions
    page_key_prefix = "bj_" if title_suffix == "(Standard)" else "plan_"
    editor_key = f"grid_editor_{page_key_prefix}_{category_key}_{stored_key}"

    num_rows = len(grid_to_edit)
    min_height = 200
    max_height = 700
    row_height_approx = 35
    calculated_height = (num_rows + 1) * row_height_approx + 3
    dynamic_height = min(max(calculated_height, min_height), max_height)

    # Configuration des colonnes
    column_config = {
        grid_to_edit.columns[0]: st.column_config.TextColumn(
            "Périmètre",
            disabled=True,
            help="Le nom du périmètre (non modifiable ici).",
            width="medium"
        )
    }
    for ts in time_slots:
        column_config[ts] = st.column_config.CheckboxColumn(ts, default=False)

    edited_df_from_widget = st.data_editor(
        grid_to_edit,
        height=dynamic_height,
        use_container_width=True,
        key=editor_key,
        num_rows="fixed",
        column_config=column_config,
        hide_index=True,
    )

    # Bouton de sauvegarde
    c1_save, c2_save = st.columns([0.3, 0.7])
    with c1_save:
        if st.button("Enregistrer les modifications 💾",
                    key=f"save_btn_{editor_key}",
                    type="primary",
                    use_container_width=True):
            try:
                edited_df_from_editor = edited_df_from_widget
                original_df = st.session_state.planning_data[category_key][stored_key]
                index_col_name = edited_df_from_editor.columns[0]
                new_df = edited_df_from_editor.set_index(index_col_name)
                new_df.index.name = original_df.index.name
                new_df = new_df.reindex(columns=time_slots, fill_value=0)
                new_df = new_df.fillna(0).astype(int).clip(0, 1)
                st.session_state.planning_data[category_key][stored_key] = new_df
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de la sauvegarde : {e}")
    with c2_save:
        st.error("Pensez à enregistrer si vous effectuez des changements dans la grille.")

    # Remplissage en masse
    with st.expander("🛠️ Remplir une plage horaire en masse"):
        df_bulk = st.session_state.planning_data[category_key][stored_key]
        all_rows = list(df_bulk.index)
        all_cols = list(df_bulk.columns)

        if not all_rows or not all_cols:
            st.info("La grille est vide ou n'a pas de créneaux horaires.")
        else:
            col_r, col_s, col_v, col_btn = st.columns([0.38, 0.42, 0.08, 0.12])
            with col_r:
                rows_sel = st.multiselect(
                    "Périmètre(s)", options=all_rows, default=[],
                    key=f"bulk_rows_{page_key_prefix}_{category_key}_{stored_key}"
                )
            with col_s:
                start_col, end_col = st.select_slider(
                    "Plage horaire", options=all_cols, value=(all_cols[0], all_cols[-1]),
                    key=f"bulk_range_{page_key_prefix}_{category_key}_{stored_key}"
                )
            with col_v:
                val_set = st.radio(
                    "Valeur", [1, 0], index=0,
                    key=f"bulk_val_{page_key_prefix}_{category_key}_{stored_key}",
                    label_visibility="collapsed"
                )
            with col_btn:
                st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
                if st.button("✅",
                           key=f"bulk_apply_{page_key_prefix}_{category_key}_{stored_key}",
                           use_container_width=True):
                    if not rows_sel:
                        st.warning("Sélectionnez au moins un périmètre.")
                    else:
                        _apply_bulk_range(category_key, stored_key, rows_sel,
                                        start_col, end_col, val_set)
                        st.success("Plage mise à jour.")
                        st.rerun()

    # KPIs
    grid_now = st.session_state.planning_data[category_key][stored_key]
    total_par_creneau = grid_now.sum(axis=0)
    total_heures = grid_now.values.sum() * 0.5
    pic_effectifs = int(total_par_creneau.max()) if not total_par_creneau.empty else 0

    st.bar_chart(total_par_creneau, height=230)
    st.markdown(
        f"""
        <div class="kpi-cards">
            <div class="kpi-card kpi-blue">
                <div class="label">Total Heures Planifiées (JT)</div>
                <div class="value">{total_heures:.1f} h</div>
            </div>
            <div class="kpi-card kpi-green">
                <div class="label">Pic Effectifs Requis (JT)</div>
                <div class="value">{pic_effectifs} agents</div>
            </div>
        </div>
        """, unsafe_allow_html=True
    )


def planning_editor_ui(category_name, category_key):
    """Interface d'édition de planification pour une catégorie"""
    perimetres = st.session_state.perimetres.get(category_key, [])
    if not perimetres:
        st.error(
            f"Aucun périmètre défini pour '{category_name}'. "
            "Ajoutez-les dans 'Configuration'."
        )
        return

    planning_dict = st.session_state.planning_data.setdefault(category_key, {})
    time_slots = TIME_SLOTS

    # Assurer qu'une grille Default existe
    if not planning_dict:
        planning_dict['Default'] = pd.DataFrame(
            0, index=perimetres, columns=time_slots
        ).astype(int)

    # Tri des jours-types
    jours_ordre = JOURS_FR + ["Default"]
    saisons_ordre = SAISONS_ORDRE

    def tri_jour_type(name: str):
        name_lower = str(name).lower()
        if name_lower == "default":
            return (len(jours_ordre), 0)
        for i, jour in enumerate(jours_ordre):
            if name_lower.startswith(jour.lower()):
                for j, saison in enumerate(saisons_ordre):
                    if saison.lower() in name_lower:
                        return (i, j)
                return (i, len(saisons_ordre))
        return (len(jours_ordre), len(saisons_ordre))

    jours_existants = sorted(list(planning_dict.keys()), key=tri_jour_type)

    selected_jour_type = st.selectbox(
        f"Sélectionner un jour-type pour **{category_name}** :",
        jours_existants,
        key=f"active_jt_{category_key}"
    )

    with st.expander("🛈"):
        st.info(
            f"Modifiez la grille **{selected_jour_type}** de **{category_name}**. "
            "Cochez les cases pour indiquer la présence. **Enregistrez avec le bouton 💾.**"
        )
        st.info("Vous pouvez aussi modifier une plage horaire en masse sous la grille.")

    # Gestion des jours-types (créer/dupliquer)
    with st.expander("Gérer les jours-types (créer/dupliquer)"):
        with st.form(key=f"form_create_jt_{category_key}"):
            st.write("**Créer ou Dupliquer un Jour-Type**")
            new_name = st.text_input(
                "Nom du nouveau jour-type (ex: 'Lundi Événement')",
                key=f"new_name_{category_key}"
            )
            source_options = ["(Partir de zéro)"] + jours_existants
            source = st.selectbox(
                "Basé sur :", source_options, index=0,
                key=f"source_{category_key}"
            )

            if st.form_submit_button("Créer / Dupliquer"):
                existants_canon = {canon(k) for k in planning_dict.keys()}
                if new_name and canon(new_name) not in existants_canon:
                    if source != "(Partir de zéro)":
                        if source in planning_dict:
                            _, source_grid = _ensure_grid(
                                planning_dict, source, perimetres, time_slots
                            )
                            new_grid = source_grid.copy()
                        else:
                            st.error(f"Le jour-type source '{source}' n'existe pas.")
                            new_grid = None
                    else:
                        new_grid = pd.DataFrame(
                            0, index=perimetres, columns=time_slots
                        ).astype(int)

                    if new_grid is not None:
                        planning_dict[new_name] = new_grid
                        st.success(f"Jour-type '{new_name}' créé.")
                        st.session_state[f"active_jt_{category_key}"] = new_name
                        st.rerun()
                elif not new_name:
                    st.error("Entrez un nom pour le nouveau jour-type.")
                else:
                    st.error(f"Un jour-type '{new_name}' existe déjà.")

    # Afficher l'éditeur
    if selected_jour_type:
        with st.container():
            _render_grid_for_edit(category_key, selected_jour_type)
