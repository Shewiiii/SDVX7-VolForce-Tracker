#include <windows.h>
#include <fcntl.h>
#include <io.h>
#include <cstdio>
#include <fstream>
#include <string>
#include <thread>
#include <atomic>
#include <chrono>
#include <regex>
#include <mutex>

const uintptr_t SCORE_WRITE_OFFSET = 0x3822A0;  // Cheat Engine
const uintptr_t DIFF_INDEX_OFFSET =
    0x1286628;  // python sdvx_rpc.py --find-diff (check
                // https://github.com/JofoxTheCat/SDVX7-Launcher/blob/main/sdvx_rpc.py)

static uintptr_t g_game_base = 0;
static uintptr_t g_hook_addr = 0;

static std::atomic<uint32_t> g_final_score{0};
static std::atomic<bool>     g_logged{false};

static std::mutex   g_state_mutex;
static std::string  g_current_state = "Menu";
static int          g_current_music_id = 0;

static HANDLE hOriginalStdout = NULL;
static HANDLE hReadPipe = NULL;
static HANDLE hWritePipe = NULL;

static void write_run_to_file() {
    uint8_t diff = 0;
    if (g_game_base != 0) {
        diff = *(uint8_t*)(g_game_base + DIFF_INDEX_OFFSET); 
    }

    int song_id = 0;
    {
        std::lock_guard<std::mutex> lock(g_state_mutex);
        song_id = g_current_music_id;
    }

    std::ofstream file("score_log.txt", std::ios::app);
    if (file.is_open()) {
        file << "{\"music_id\": " << song_id
             << ", \"diff_idx\": " << (int)diff
             << ", \"score\": " << g_final_score.load()
             << "}\n";
        file.flush();
    }
}

static LONG WINAPI VectoredHandler(PEXCEPTION_POINTERS pExceptionInfo) {
    if (pExceptionInfo->ExceptionRecord->ExceptionCode == EXCEPTION_BREAKPOINT) {
        if ((uintptr_t)pExceptionInfo->ExceptionRecord->ExceptionAddress == g_hook_addr) {
            uint32_t score = (uint32_t)(pExceptionInfo->ContextRecord->Rdx & 0xFFFFFFFF);
            uintptr_t rcx = pExceptionInfo->ContextRecord->Rcx;
            
            if (rcx != 0) {
                *(uint32_t*)(rcx + 0x4C) = score;
            }
            if (score > 0) {
                g_final_score.store(score);
            }

            pExceptionInfo->ContextRecord->Rip += 3;
            return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static void install_veh_hook() {
    HMODULE hMod = NULL;
    while ((hMod = GetModuleHandleW(L"soundvoltex.dll")) == NULL) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    g_game_base = (uintptr_t)hMod;
    g_hook_addr = g_game_base + SCORE_WRITE_OFFSET;
    AddVectoredExceptionHandler(1, VectoredHandler);

    DWORD oldProtect;
    if (VirtualProtect((LPVOID)g_hook_addr, 1, PAGE_EXECUTE_READWRITE, &oldProtect)) {
        *(uint8_t*)g_hook_addr = 0xCC;
        VirtualProtect((LPVOID)g_hook_addr, 1, oldProtect, &oldProtect);
        FlushInstructionCache(GetCurrentProcess(), (LPCVOID)g_hook_addr, 1);
    }
}

static void parse_line(const std::string& line) {
    static const std::regex rx_song(R"(music/(\d+)_)", std::regex::optimize);

    std::lock_guard<std::mutex> lock(g_state_mutex);

    // 1. Song ID detection matching the reference state logic
    if (line.find("Loading /data/music/") != std::string::npos &&
        line.find(".png") != std::string::npos) {

        std::smatch match_song;
        if (std::regex_search(line, match_song, rx_song)) {
            std::string sid_str = match_song[1];

            // Select-screen backgrounds (_b.png) load asynchronously and can arrive late
            bool is_bg_load = line.find("_b.png") != std::string::npos;
            if (is_bg_load && g_current_state == "Playing") {
                return;
            }

            if (is_bg_load || g_current_state == "Playing") {
                try {
                    g_current_music_id = std::stoi(sid_str);
                } catch (...) {}
            }
        }
    }

    // 2. Music select scene
    if (line.find("in MUSICSELECT") != std::string::npos) {
        if (g_current_state != "Selecting") {
            g_current_state = "Selecting";
        }
    }

    // 3. Gameplay scene
    if (line.find("in ALTERNATIVE_GAME_SCENE") != std::string::npos ||
        line.find("in MEGAMIX_GAME_SCENE") != std::string::npos ||
        line.find("in MEGAMIX_BATTLE") != std::string::npos ||
        line.find("in BATTLE_GAME_SCENE") != std::string::npos ||
        line.find("in AUTOMATION_GAME_SCENE") != std::string::npos ||
        line.find("in ARENA_GAME_SCENE") != std::string::npos ||
        line.find("game_bg/") != std::string::npos) {

        if (g_current_state != "Playing") {
            g_current_state = "Playing";
            g_final_score.store(0);
            g_logged.store(false);
        }
    }

    // 4. Result scene
    if (line.find("in RESULT_SCENE") != std::string::npos) {
        if (g_current_state != "Results") {
            g_current_state = "Results";
            if (!g_logged.exchange(true)) {
                std::thread([]() {
                    std::this_thread::sleep_for(std::chrono::milliseconds(300));
                    if (g_final_score.load() > 0) {
                        write_run_to_file();
                    }
                }).detach();
            }
        }
    }

    // 5. Menu reset
    if (line.find("in GAMEOVER") != std::string::npos ||
        line.find("in CARD_OUT_SCENE") != std::string::npos ||
        line.find("in TITLEDEMO") != std::string::npos) {
        if (g_current_state != "Menu") {
            g_current_state = "Menu";
        }
    }
}

static void log_reader_thread() {
    char buffer[4096];
    DWORD bytesRead;
    std::string line_buffer;

    while (ReadFile(hReadPipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL)) {
        if (bytesRead == 0) continue;
        buffer[bytesRead] = '\0';

        if (hOriginalStdout && hOriginalStdout != INVALID_HANDLE_VALUE && hOriginalStdout != hWritePipe) {
            DWORD written;
            WriteFile(hOriginalStdout, buffer, bytesRead, &written, NULL);
        }

        line_buffer += buffer;
        size_t pos_nl = 0;
        while ((pos_nl = line_buffer.find('\n')) != std::string::npos) {
            std::string line = line_buffer.substr(0, pos_nl);
            line_buffer.erase(0, pos_nl + 1);

            if (!line.empty() && line.back() == '\r') line.pop_back();
            parse_line(line);
        }
    }
}

static void setup_stdout_hook() {
    hOriginalStdout = GetStdHandle(STD_OUTPUT_HANDLE);

    SECURITY_ATTRIBUTES sa;
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = NULL;

    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) return;

    SetStdHandle(STD_OUTPUT_HANDLE, hWritePipe);
    SetStdHandle(STD_ERROR_HANDLE, hWritePipe);

    int fd = _open_osfhandle((intptr_t)hWritePipe, _O_TEXT);
    if (fd != -1) {
        FILE *fp = _fdopen(fd, "w");
        if (fp) {
            *stdout = *fp;
            *stderr = *fp;
            setvbuf(stdout, NULL, _IONBF, 0);
            setvbuf(stderr, NULL, _IONBF, 0);
        }
    }

    std::thread(log_reader_thread).detach();
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    if (ul_reason_for_call == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        setup_stdout_hook();
        std::thread(install_veh_hook).detach();
    }
    return TRUE;
}