package com.simlect.component;
import org.junit.jupiter.api.Test;
import org.springframework.ai.embedding.observation.EmbeddingModelObservationContext;
import org.springframework.ai.embedding.*;
import io.micrometer.observation.Observation;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class EmbeddingUsageObserverTest {
    @Test void onlyEmbeddingContextsAndMissingProviderUsageAreSafe(){
        var observer=new EmbeddingUsageObserver();assertFalse(observer.supportsContext(new Observation.Context()));
        var context=EmbeddingModelObservationContext.builder().embeddingRequest(new EmbeddingRequest(List.of("TEST ONLY"),null)).provider("test").build();
        assertTrue(observer.supportsContext(context));assertDoesNotThrow(()->observer.onStop(context));
        context.setResponse(new EmbeddingResponse(List.of(new Embedding(new float[1024],0))));assertDoesNotThrow(()->observer.onStop(context));
    }
}
