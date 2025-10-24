"""
Page Configuration - Gestion des paramètres de base
"""
import pandas as pd
import streamlit as st


def render_configuration_page():
    """Affiche la page de configuration"""
    st.title("Configuration Générale")
    st.markdown("Modifiez ici les paramètres de base qui alimentent tous les calculs de planification.")

    # Bloc 1 : Personnel et Tarifs
    with st.expander("1 - Personnel et Tarifs Horaires", expanded=True):
        st.info(
            "🛈 Définissez ici les différents types de personnel et leur coût horaire. "
            "Ces tarifs seront utilisés pour calculer le coût du budget annuel."
        )
        if 'personnel' not in st.session_state or not isinstance(st.session_state.personnel, pd.DataFrame):
            st.warning("Données personnel non initialisées.")
        else:
            editor_personnel_key = "editor_personnel_config"
            personnel_before_edit = st.session_state.personnel.copy()
            edited_personnel = st.data_editor(
                personnel_before_edit,
                num_rows="dynamic",
                key=editor_personnel_key,
                use_container_width=True,
                column_config={
                    "Type": st.column_config.TextColumn("Type", required=True),
                    "Coût Horaire": st.column_config.NumberColumn(
                        "Coût Horaire (CHF)", format="%.2f", required=True, min_value=0.0
                    )
                },
                hide_index=True
            )
            if not edited_personnel.equals(personnel_before_edit):
                st.session_state.personnel = edited_personnel.copy()
                st.rerun()

    # Bloc 2 : Périmètres
    with st.expander("2 - Gestion des Périmètres par Catégorie", expanded=False):
        st.info(
            "🛈 Listez ici tous les postes ou zones opérationnelles ('Périmètres') et "
            "regroupez-les par 'Catégorie' - **utilisez les types de personnel définis en 1.** "
            "C'est essentiel pour organiser la planification."
        )
        if 'perimetres' not in st.session_state or not st.session_state.perimetres:
            st.warning("Données périmètres non initialisées.")
        else:
            all_categories = sorted(list(st.session_state.perimetres.keys()))
            categories_options = ["Toutes"] + all_categories

            selected_category_filter = st.selectbox(
                "Filtrer Catégorie (pour affichage/édition):",
                categories_options,
                key="perimetre_filter_select"
            )

            # Créer DataFrame avant éditeur
            perimetres_list_before = [
                {'Categorie': c, 'Perimetre': p}
                for c, items in st.session_state.perimetres.items()
                for p in items
            ]
            perimetres_df_full_before = pd.DataFrame(perimetres_list_before)

            if selected_category_filter != "Toutes":
                df_to_display = perimetres_df_full_before[
                    perimetres_df_full_before['Categorie'] == selected_category_filter
                ].copy()
            else:
                df_to_display = perimetres_df_full_before.copy()

            st.markdown("Ajoutez, modifiez ou supprimez des périmètres:")
            editor_perimetres_key = "editor_perimetres_widget"

            edited_part = st.data_editor(
                df_to_display,
                num_rows="dynamic",
                use_container_width=True,
                key=editor_perimetres_key,
                column_config={
                    "Categorie": st.column_config.TextColumn(
                        "Catégorie", help="Entrez un nom existant ou nouveau.", required=True
                    ),
                    "Perimetre": st.column_config.TextColumn("Périmètre", required=True)
                },
                hide_index=True,
            )

            # Logique de mise à jour
            if not edited_part.equals(df_to_display):
                try:
                    # Nettoyer les données éditées
                    edited_part_cleaned = edited_part.dropna(subset=['Perimetre', 'Categorie'])
                    edited_part_cleaned['Categorie'] = edited_part_cleaned['Categorie'].astype(str).str.strip()
                    edited_part_cleaned['Perimetre'] = edited_part_cleaned['Perimetre'].astype(str).str.strip()
                    edited_part_cleaned = edited_part_cleaned[edited_part_cleaned['Perimetre'] != '']
                    edited_part_cleaned = edited_part_cleaned[edited_part_cleaned['Categorie'] != '']
                    edited_part_cleaned = edited_part_cleaned.drop_duplicates(
                        subset=['Categorie', 'Perimetre']
                    )

                    # Reconstruire le DataFrame complet
                    if selected_category_filter != "Toutes":
                        other_categories_df = perimetres_df_full_before[
                            perimetres_df_full_before['Categorie'] != selected_category_filter
                        ]
                        reconstructed_df = pd.concat(
                            [other_categories_df, edited_part_cleaned], ignore_index=True
                        )
                    else:
                        reconstructed_df = edited_part_cleaned

                    # Reconstruire le dictionnaire final
                    final_categories = sorted(reconstructed_df['Categorie'].unique().tolist())
                    new_perimetres_dict = {cat: [] for cat in final_categories}

                    if not reconstructed_df.empty:
                        grouped = reconstructed_df.groupby('Categorie')['Perimetre'].apply(list)
                        for cat, items in grouped.items():
                            new_perimetres_dict[cat] = sorted(items)

                    # Comparer et mettre à jour
                    current_perimetres_sorted = {
                        k: sorted(v) for k, v in st.session_state.get('perimetres', {}).items()
                    }
                    new_perimetres_sorted = {
                        k: sorted(v) for k, v in new_perimetres_dict.items()
                    }

                    if current_perimetres_sorted != new_perimetres_sorted:
                        st.session_state.perimetres = new_perimetres_dict
                        for cat in new_perimetres_dict:
                            st.session_state.planning_data.setdefault(cat, {})
                        st.rerun()

                except Exception as e:
                    st.error(f"Erreur lors de la mise à jour des périmètres : {e}")

    # Bloc 3 : Saisons de Référence
    with st.expander("3 - Saisons de Référence", expanded=False):
        st.info(
            "🛈 Définissez les dates des saisons pour une année de référence (ex: 2026). "
            "Ces dates serviront de modèle pour calculer automatiquement les calendriers "
            "des années futures."
        )
        if 'saisons' not in st.session_state or not isinstance(st.session_state.saisons, pd.DataFrame):
            st.warning("Données saisons non initialisées.")
        else:
            st.markdown(f"Année de référence: **{st.session_state.get('reference_year_saisons', 'N/A')}**")
            try:
                df_saisons_before_edit = st.session_state.saisons.copy()
                df_saisons_to_edit = df_saisons_before_edit.copy()
                df_saisons_to_edit['Date Début'] = pd.to_datetime(
                    df_saisons_to_edit['Date Début'], errors='coerce'
                ).dt.date
                df_saisons_to_edit['Date Fin'] = pd.to_datetime(
                    df_saisons_to_edit['Date Fin'], errors='coerce'
                ).dt.date
                df_saisons_to_edit.dropna(subset=['Date Début', 'Date Fin'], inplace=True)

                editor_saisons_key = "editor_saisons_config"
                edited_saisons = st.data_editor(
                    df_saisons_to_edit,
                    column_config={
                        "Saison": st.column_config.TextColumn("Saison", required=True),
                        "Date Début": st.column_config.DateColumn(
                            "Début", format="DD/MM/YYYY", required=True
                        ),
                        "Date Fin": st.column_config.DateColumn(
                            "Fin", format="DD/MM/YYYY", required=True
                        )
                    },
                    num_rows="dynamic",
                    key=editor_saisons_key,
                    use_container_width=True,
                    hide_index=True
                )
                if not edited_saisons.equals(df_saisons_to_edit):
                    edited_saisons['Date Début'] = pd.to_datetime(edited_saisons['Date Début']).dt.date
                    edited_saisons['Date Fin'] = pd.to_datetime(edited_saisons['Date Fin']).dt.date
                    st.session_state.saisons = edited_saisons.copy()
                    if not edited_saisons.empty:
                        st.session_state.reference_year_saisons = edited_saisons['Date Début'].iloc[0].year
                    st.rerun()

            except Exception as e:
                st.error(f"Erreur saisons: {e}")
