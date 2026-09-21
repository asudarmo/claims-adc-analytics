{#
  Use the custom schema name exactly as given (staging / intermediate /
  marts), instead of dbt's default "<target_schema>_<custom_schema>"
  prefixing - this project names its Postgres schemas by pipeline layer
  (see docs/SCHEMA_DESIGN.md), not by dbt target.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
