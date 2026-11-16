begin;

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.usuarios u
        join public.roles r on r.id = u.rol_id
        where u.id = (select auth.uid())
          and r.codigo = 'administrador'
    );
$$;

revoke all on function public.is_admin() from public;
revoke all on function public.is_admin() from anon;
grant execute on function public.is_admin() to authenticated;

create or replace function public.admin_set_report_state(
    p_reporte_id bigint,
    p_estado_codigo text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_estado_id bigint;
    v_filas_actualizadas integer;
begin
    if not public.is_admin() then
        raise exception 'Se requiere el rol de administrador'
            using errcode = '42501';
    end if;

    if p_estado_codigo not in ('activo', 'resuelto') then
        raise exception 'Estado de reporte no permitido'
            using errcode = '22023';
    end if;

    select id into v_estado_id
    from public.estados_reporte
    where codigo = p_estado_codigo;

    if v_estado_id is null then
        raise exception 'No existe el estado de reporte solicitado'
            using errcode = '22023';
    end if;

    update public.reportes
    set estado_id = v_estado_id
    where id = p_reporte_id;

    get diagnostics v_filas_actualizadas = row_count;
    return v_filas_actualizadas > 0;
end;
$$;

revoke all on function public.admin_set_report_state(bigint, text) from public;
revoke all on function public.admin_set_report_state(bigint, text) from anon;
grant execute on function public.admin_set_report_state(bigint, text)
    to authenticated;

drop policy if exists "Users can view active or their own reports" on public.reportes;
create policy "Users can view active or their own reports"
    on public.reportes for select to authenticated
    using (
        usuario_id = (select auth.uid())
        or public.is_admin()
        or exists (
            select 1 from public.estados_reporte e
            where e.id = reportes.estado_id and e.codigo = 'activo'
        )
    );

drop policy if exists "Administrators can update reports" on public.reportes;
create policy "Administrators can update reports"
    on public.reportes for update to authenticated
    using (public.is_admin())
    with check (public.is_admin());

notify pgrst, 'reload schema';
commit;
