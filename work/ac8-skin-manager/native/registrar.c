/* Offline development bridge for the verified AC8 1.1.2 package-store ABI.
 * Containers are mounted by AC8OverrideLoader. This adds only their independent
 * texture package records to the existing package store under its engine lock.
 * No hooks, code patches, signature changes, or stock asset overrides.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include "engine_build.h"

typedef struct { void *data; int32_t num, max; } Array;
typedef struct { uint64_t id; Array ids, entries, optional_ids, optional_entries,
    redirect_names, localized, redirects; } Header;
typedef struct { Header *header; uint32_t order, sequence; Array localized; } Mounted;
_Static_assert(sizeof(Header)==0x78, "Container header ABI");
_Static_assert(sizeof(Mounted)==32, "Mounted-container ABI");
_Static_assert(sizeof(Array)==16, "Array ABI");
static HMODULE own_module;
enum { PATH_CAPACITY = 32768 };
static wchar_t directory[PATH_CAPACITY];
static int observed_num,observed_capacity;
static int already_count,failed_count;
static void *engine_heap;
static void *(*engine_alloc)(void*,size_t,uint32_t);
static void (*engine_free)(void*);
static void *(*cached_find)(void*,uint64_t);

static int readable(const void *pointer, size_t length) {
    if (!pointer || !length || (uintptr_t)pointer+length < (uintptr_t)pointer) return 0;
    MEMORY_BASIC_INFORMATION memory;
    if (!VirtualQuery(pointer,&memory,sizeof(memory)) || memory.State!=MEM_COMMIT
        || (memory.Protect&(PAGE_NOACCESS|PAGE_GUARD))) return 0;
    return (uintptr_t)pointer+length <= (uintptr_t)memory.BaseAddress+memory.RegionSize;
}
static int writable(void *pointer, size_t length) {
    MEMORY_BASIC_INFORMATION memory;
    if (!readable(pointer,length) || !VirtualQuery(pointer,&memory,sizeof(memory))) return 0;
    return (memory.Protect & (PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))!=0;
}
static void status(const char *state, const char *detail, int count) {
    wchar_t path[PATH_CAPACITY];
    if (swprintf(path,PATH_CAPACITY,L"%lsregistrar-status.json",directory)<0) return;
    char output[768];
    int size=snprintf(output,sizeof(output),"{\"revision\":\"20261008-cached-store\",\"state\":\"%s\",\"detail\":\"%s\",\"registered\":%d,\"already\":%d,\"failed\":%d,\"containers\":%d,\"capacity\":%d}\n",state,detail,count,already_count,failed_count,observed_num,observed_capacity);
    if (size<0 || (size_t)size>=sizeof(output)) return;
    HANDLE file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if (file!=INVALID_HANDLE_VALUE) { DWORD written;WriteFile(file,output,(DWORD)size,&written,NULL);CloseHandle(file); }
}
static uint32_t u32(const unsigned char *p) { uint32_t v;memcpy(&v,p,4);return v; }
static uint64_t u64(const unsigned char *p) { uint64_t v;memcpy(&v,p,8);return v; }

/* A texture-only UE5.4 header: version 3, no package imports, shader maps,
 * optional segments, name redirects or localized packages. Refuse other ABIs.
 */
static Header *parse_header(const unsigned char *data, size_t size) {
    if (size<36 || u32(data)!=0x496f436e || u32(data+4)!=3) return NULL;
    uint32_t count=u32(data+16);
    if (!count || count>4096 || !u64(data+8) || size!=56+(size_t)count*24) return NULL;
    size_t at=20+(size_t)count*8;
    uint32_t entries=u32(data+at);at+=4;
    if (entries!=count*16) return NULL;
    for (size_t i=at;i<size;i++) if (data[i]) return NULL;
    for (uint32_t i=0;i<count;i++) {
        uint64_t id=u64(data+20+i*8);
        if (!id) return NULL;
        for (uint32_t j=0;j<i;j++) if (id==u64(data+20+j*8)) return NULL;
    }
    size_t allocation=sizeof(Header)+(size_t)count*8+entries;
    Header *header=VirtualAlloc(NULL,allocation,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    if (!header) return NULL;
    header->id=u64(data+8);
    header->ids=(Array){(unsigned char*)header+sizeof(Header),(int32_t)count,(int32_t)count};
    header->entries=(Array){(unsigned char*)header->ids.data+count*8,(int32_t)entries,(int32_t)entries};
    memcpy(header->ids.data,data+20,count*8);
    memcpy(header->entries.data,data+at,entries);
    return header;
}
__declspec(dllexport) int validate_header(const unsigned char *data, size_t size) {
    Header *header=parse_header(data,size);if (!header) return 0;
    VirtualFree(header,0,MEM_RELEASE);return 1;
}

static int contains(Header *header,uint64_t package) {
    if (!readable(header,sizeof(Header)) || header->ids.num<0 || header->ids.num>1000000
        || header->ids.max<header->ids.num || header->entries.num<header->ids.num*16
        || header->entries.max<header->entries.num) return -1;
    if (!header->ids.num) return 0;
    if (!readable(header->ids.data,(size_t)header->ids.num*8)) return -1;
    uint64_t *ids=header->ids.data;
    for (int i=0;i<header->ids.num;i++) if (ids[i]==package) return 1;
    return 0;
}

/* Native index construction consumes and frees these arrays. Give the engine
 * three independent allocations from its own allocator, exactly like Mount().
 * VirtualAlloc is used only for the temporary parser, never engine-owned data.
 */
static Header *engine_copy(const Header *source) {
    Header *copy=engine_alloc(engine_heap,sizeof(Header),16);
    if (!copy) return NULL;
    memset(copy,0,sizeof(*copy));copy->id=source->id;
    copy->ids=source->ids;copy->entries=source->entries;
    copy->ids.data=engine_alloc(engine_heap,(size_t)source->ids.num*8,16);
    copy->entries.data=engine_alloc(engine_heap,(size_t)source->entries.num,16);
    if (!copy->ids.data || !copy->entries.data) {
        engine_free(copy->ids.data);engine_free(copy->entries.data);engine_free(copy);return NULL;
    }
    memcpy(copy->ids.data,source->ids.data,(size_t)source->ids.num*8);
    memcpy(copy->entries.data,source->entries.data,(size_t)source->entries.num);
    return copy;
}
static void discard_copy(Header *header) {
    engine_free(header->ids.data);engine_free(header->entries.data);engine_free(header);
}

/* Lua C function: return zero Lua results. Lua reads the diagnostic JSON. */
__declspec(dllexport) int register_packages(void *lua_state) {
    (void)lua_state;
    if (!directory[0]) {
        DWORD length=GetModuleFileNameW(own_module,directory,PATH_CAPACITY);
        if (!length || length>=PATH_CAPACITY-64) { directory[0]=0;return 0; }
        wchar_t *end=wcsrchr(directory,L'\\');if (!end) return 0;end[1]=0;
    }
    observed_num=observed_capacity=already_count=failed_count=0;
    wchar_t offline[8];
    if (GetEnvironmentVariableW(L"EOS_USE_ANTICHEATCLIENTNULL",offline,8)!=1 || offline[0]!=L'1') {
        status("blocked","Offline launch environment required",0);return 0;
    }
    unsigned char *base=(unsigned char*)GetModuleHandleW(L"AceCombat8.exe");
    if (!base || !readable(base,0x1000)) { status("blocked","Game module unavailable",0);return 0; }
    IMAGE_DOS_HEADER *dos=(IMAGE_DOS_HEADER*)base;
    if (dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<0 || dos->e_lfanew>0x1000) {
        status("blocked","Invalid game executable header",0);return 0;
    }
    IMAGE_NT_HEADERS64 *pe=(IMAGE_NT_HEADERS64*)(base+dos->e_lfanew);
    if (pe->Signature!=IMAGE_NT_SIGNATURE || pe->FileHeader.TimeDateStamp!=ENGINE_TIMESTAMP
        || pe->OptionalHeader.SizeOfImage!=ENGINE_IMAGE_SIZE
        || memcmp(base+0x27e9ad0,GETTER_BYTES,sizeof(GETTER_BYTES))
        || memcmp(base+0x171dc10,MANAGER_BYTES,sizeof(MANAGER_BYTES))
        || memcmp(base+0x171d8a0,FIND_BYTES,sizeof(FIND_BYTES))
        || memcmp(base+0x27dde50,INDEX_FIND_BYTES,sizeof(INDEX_FIND_BYTES))
        || memcmp(base+0x27de0d0,BEGIN_READ_BYTES,sizeof(BEGIN_READ_BYTES))
        || memcmp(base+0x27de100,END_READ_BYTES,sizeof(END_READ_BYTES))
        || memcmp(base+0x1724c20,FREE_BYTES,sizeof(FREE_BYTES))) {
        status("blocked","Engine build does not match verified ABI",0);return 0;
    }
    void *(*manager_get)(void)=(void*(*)(void))(base+0x171dc10);
    void *(*manager_find)(void*,const wchar_t*)=(void*(*)(void*,const wchar_t*))(base+0x171d8a0);
    unsigned char *pak=manager_find(manager_get(),L"PakFile");
    if (!readable(pak,0xf0)) { status("waiting","Pak platform not ready",0);return 0; }
    uintptr_t *vtable=*(uintptr_t**)pak;
    if (!readable(vtable,0x78) || vtable[0x70/8]!=(uintptr_t)(base+0x27e9ad0)) {
        status("blocked","Unexpected platform-file vtable",0);return 0;
    }
    unsigned char *backend=*(unsigned char**)(pak+0xe0);
    if (!writable(backend,0x120)) { status("waiting","Package backend not ready",0);return 0; }
    uintptr_t backend_vtable=*(uintptr_t*)backend;
    if (backend_vtable<(uintptr_t)base || backend_vtable>=(uintptr_t)base+ENGINE_IMAGE_SIZE
        || backend[0x118]>1 || !readable((void*)backend_vtable,0x28)
        || ((uintptr_t*)backend_vtable)[2]!=(uintptr_t)(base+0x27de0d0)
        || ((uintptr_t*)backend_vtable)[3]!=(uintptr_t)(base+0x27de100)
        || ((uintptr_t*)backend_vtable)[4]!=(uintptr_t)(base+0x27de110)) {
        status("blocked","Unexpected package backend",0);return 0;
    }
    engine_heap=*(void**)(base+0xe426090);
    if (!readable(engine_heap,sizeof(void*)) || !readable(*(void**)engine_heap,0x50)) {
        status("waiting","Engine allocator unavailable",0);return 0;
    }
    engine_alloc=(void*(*)(void*,size_t,uint32_t))(*(uintptr_t**)engine_heap)[0x28/8];
    engine_free=(void(*)(void*))(base+0x1724c20);
    cached_find=(void*(*)(void*,uint64_t))(base+0x27dde50);
    void (*begin_read)(void*)=(void(*)(void*))(base+0x27de0d0);
    void (*end_read)(void*)=(void(*)(void*))(base+0x27de100);
    /* BeginRead runs the native rebuild when dirty; use its matching EndRead. */
    begin_read(backend);
    int stock_found=cached_find(backend+0x50,UINT64_C(0x549fe1ca19d5ca76))!=NULL;
    end_read(backend);
    if (!stock_found) { status("waiting","Stock package absent from cached index",0);return 0; }
    Array *containers=(Array*)(backend+0x38);
    SRWLOCK *lock=(SRWLOCK*)(backend+8);
    AcquireSRWLockExclusive(lock);
    observed_num=containers->num;observed_capacity=containers->max;
    int ok=containers->num>0 && containers->num<=128 && containers->max>=containers->num
        && containers->max<=1024 && writable(containers->data,(size_t)containers->max*sizeof(Mounted));
    Mounted *items=containers->data;
    if (ok) for (int i=0;i<containers->num;i++) {
        int found=contains(items[i].header,UINT64_C(0x549fe1ca19d5ca76));
        if (found<0) { ok=0;break; }
    }
    if (!ok) {
        ReleaseSRWLockExclusive(lock);status("blocked","Mounted-container layout invalid",0);return 0;
    }
    ReleaseSRWLockExclusive(lock);

    wchar_t search[PATH_CAPACITY];
    if (swprintf(search,PATH_CAPACITY,L"%lscontainers\\*.bin",directory)<0) { status("blocked","Header path too long",0);return 0; }
    WIN32_FIND_DATAW file_data;HANDLE search_handle=FindFirstFileW(search,&file_data);
    if (search_handle==INVALID_HANDLE_VALUE) { status("blocked","No independent package headers",0);return 0; }
    int registered=0,already=0,failed=0;
    uint64_t pending_ids[4096];int pending_count=0;
    do {
        if (file_data.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) continue;
        wchar_t filename[PATH_CAPACITY];
        if (swprintf(filename,PATH_CAPACITY,L"%lscontainers\\%ls",directory,file_data.cFileName)<0) { failed++;continue; }
        HANDLE file=CreateFileW(filename,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
        if (file==INVALID_HANDLE_VALUE) { failed++;continue; }
        DWORD size=GetFileSize(file,NULL),got=0;
        unsigned char *data=size<1024*1024?HeapAlloc(GetProcessHeap(),0,size):NULL;
        int read_ok=data && ReadFile(file,data,size,&got,NULL) && got==size;CloseHandle(file);
        Header *header=read_ok?parse_header(data,size):NULL;
        if (data) HeapFree(GetProcessHeap(),0,data);
        if (!header) { failed++;continue; }
        Header *owned=engine_copy(header);
        if (!owned || pending_count+header->ids.num>4096) {
            if (owned) discard_copy(owned);
            VirtualFree(header,0,MEM_RELEASE);failed++;continue;
        }
        AcquireSRWLockExclusive(lock);
        items=containers->data;
        if (containers->num<1 || containers->num>128 || containers->max<containers->num
            || containers->max>1024 || !writable(items,(size_t)containers->max*sizeof(Mounted))) {
            ReleaseSRWLockExclusive(lock);discard_copy(owned);VirtualFree(header,0,MEM_RELEASE);failed++;break;
        }
        int exists=0,overlap=0,added=0;
        uint32_t order=999;
        for (int i=0;i<containers->num;i++) {
            if (items[i].header->id==header->id) exists=1;
            if (items[i].order>order) order=items[i].order;
            for (int j=0;j<header->ids.num;j++)
                if (contains(items[i].header,((uint64_t*)header->ids.data)[j])!=0) overlap=1;
        }
        /* Most native headers are empty after indexing. Check the live lookup
         * as well as not-yet-consumed headers when detecting collisions. */
        for (int j=0;j<header->ids.num;j++)
            if (cached_find(backend+0x50,((uint64_t*)header->ids.data)[j])) overlap=1;
        if (exists) already++;
        else if (overlap || containers->num>=containers->max || order>=0x7ffffffe) failed++;
        else {
            /* Engine order is descending, then newest sequence first. */
            memmove(items+1,items,(size_t)containers->num*sizeof(Mounted));
            Mounted record={0};record.header=owned;record.order=order+1;
            record.sequence=(uint32_t)InterlockedIncrement((volatile LONG*)(backend+0x48))-1;
            items[0]=record;containers->num++;
            *(volatile unsigned char*)(backend+0x118)=1;
            registered++;
            added=1;
            observed_num=containers->num;
        }
        ReleaseSRWLockExclusive(lock);
        if (added || exists) for (int j=0;j<header->ids.num;j++) pending_ids[pending_count++]=((uint64_t*)header->ids.data)[j];
        if (!added) discard_copy(owned);
        VirtualFree(header,0,MEM_RELEASE);
    } while (FindNextFileW(search_handle,&file_data));
    FindClose(search_handle);
    if (registered) { HMODULE pin;GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCWSTR)&register_packages,&pin); }
    if (pending_count) {
        begin_read(backend);
        for (int i=0;i<pending_count;i++) if (!cached_find(backend+0x50,pending_ids[i])) failed++;
        end_read(backend);
    }
    already_count=already;failed_count=failed;
    status(failed?"partial":registered?"registered":already?"already-registered":"blocked",
        failed?"Some headers refused: format, overlap or capacity":"Independent texture packages available",registered);
    return 0;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved) {
    (void)reserved;if (reason==DLL_PROCESS_ATTACH) { own_module=instance;DisableThreadLibraryCalls(instance); }return TRUE;
}
