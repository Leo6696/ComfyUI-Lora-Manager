import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Ensure globals are defined before importing module under test
const ORIGINAL_REQUEST_ANIMATION_FRAME = global.requestAnimationFrame;

class MockIntersectionObserver {
    static instances = [];

    constructor(callback, options) {
        this.callback = callback;
        this.options = options;
        this.observed = new Set();
        MockIntersectionObserver.instances.push(this);
    }

    observe(element) {
        this.observed.add(element);
    }

    unobserve(element) {
        this.observed.delete(element);
    }

    disconnect() {
        this.observed.clear();
    }

    trigger(entries) {
        this.callback(entries, this);
    }
}

describe('ModelCard video lazy loading queue', () => {
    let configureModelCardVideo;
    let getModelPublishedDate;
    let loadSpy;
    let pauseSpy;
    let playSpy;

    beforeEach(async () => {
        vi.useFakeTimers();
        vi.setSystemTime(0);

        MockIntersectionObserver.instances = [];
        global.IntersectionObserver = MockIntersectionObserver;
        global.requestAnimationFrame = (callback) => setTimeout(callback, 0);

        ({ configureModelCardVideo, getModelPublishedDate } = await import('../../../static/js/components/shared/ModelCard.js'));

        loadSpy = vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(function () {
            this.dataset.loadCalls = `${parseInt(this.dataset.loadCalls || '0', 10) + 1}`;
            this.dataset.loadCallTime = `${Date.now()}`;
        });

        pauseSpy = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
        playSpy = vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve());
    });

    afterEach(() => {
        loadSpy.mockRestore();
        pauseSpy.mockRestore();
        playSpy.mockRestore();
        vi.useRealTimers();
        delete global.IntersectionObserver;
        if (ORIGINAL_REQUEST_ANIMATION_FRAME) {
            global.requestAnimationFrame = ORIGINAL_REQUEST_ANIMATION_FRAME;
        } else {
            delete global.requestAnimationFrame;
        }
    });

    it('throttles large batches of intersecting videos', async () => {
        const container = document.createElement('div');
        document.body.appendChild(container);

        const videoCount = 10;
        const videos = [];

        for (let index = 0; index < videoCount; index += 1) {
            const preview = document.createElement('div');
            preview.className = 'card-preview';

            const video = document.createElement('video');
            video.dataset.src = `video-${index}.mp4`;

            const source = document.createElement('source');
            source.dataset.src = `video-${index}.mp4`;

            video.appendChild(source);
            preview.appendChild(video);
            container.appendChild(preview);

            configureModelCardVideo(video, false);
            videos.push(video);
        }

        const observer = MockIntersectionObserver.instances.at(-1);
        observer.trigger(videos.map((video) => ({ target: video, isIntersecting: true })));

        // Drain any immediate timers for the initial batch
        await vi.runOnlyPendingTimersAsync();

        // Advance timers to drain remaining batches at the paced interval
        while (videos.some((video) => video.dataset.loaded !== 'true')) {
            await vi.advanceTimersByTimeAsync(120);
            await vi.runOnlyPendingTimersAsync();
        }

        const allLoaded = videos.every((video) => video.dataset.loaded === 'true');
        expect(allLoaded).toBe(true);

        const loadTimes = videos.map((video) => Number.parseInt(video.dataset.loadCallTime || '0', 10));
        const uniqueIntervals = new Set(loadTimes);
        expect(uniqueIntervals.size).toBeGreaterThan(1);

        const loadsPerInterval = loadTimes.reduce((accumulator, time) => {
            const nextAccumulator = accumulator;
            nextAccumulator[time] = (nextAccumulator[time] || 0) + 1;
            return nextAccumulator;
        }, {});

        const maxLoadsInInterval = Math.max(...Object.values(loadsPerInterval));
        expect(maxLoadsInInterval).toBeLessThanOrEqual(2);

        document.body.removeChild(container);
    });

    it('uses publishedAt and falls back to createdAt for card dates', () => {
        expect(getModelPublishedDate({
            publishedAt: '2025-08-17T12:34:56Z',
            createdAt: '2025-08-16T12:34:56Z'
        })).toMatchObject({
            displayDate: '2025-08-17',
            isCreatedAtFallback: false
        });

        expect(getModelPublishedDate({
            createdAt: '2024-03-02T00:00:00Z'
        })).toMatchObject({
            displayDate: '2024-03-02',
            isCreatedAtFallback: true
        });

        expect(getModelPublishedDate({ publishedAt: 'not-a-date' })).toBeNull();
        expect(getModelPublishedDate({})).toBeNull();
    });
});
